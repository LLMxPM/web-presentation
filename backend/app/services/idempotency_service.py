"""文件功能：实现单事务先占位关联幂等服务，保障 External API 写操作与 Mutation Job 的防重放与并发隔离。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import normalize_utc, utc_now
from app.db.session import get_session_factory
from app.models.api_idempotency_record import ApiIdempotencyRecord

logger = logging.getLogger(__name__)

T = TypeVar("T")

SQLITE_BUSY_RETRIES = 3
SQLITE_BACKOFF_DELAYS = [0.05, 0.1, 0.2]


class IdempotencyService:
    """提供单事务先占位幂等控制。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    @staticmethod
    def calculate_request_fingerprint(
        *,
        http_method: str,
        path: str,
        payload_bytes: bytes | None = None,
        json_data: Any | None = None,
    ) -> str:
        """计算规范化请求指纹（严格排除 Authorization 与 Idempotency-Key 头）。"""

        normalized_method = http_method.upper().strip()
        normalized_path = path.strip().rstrip("/") or "/"

        if json_data is not None:
            canonical_content = json.dumps(
                json_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
            ).encode("utf-8")
        elif payload_bytes is not None:
            canonical_content = payload_bytes
        else:
            canonical_content = b""

        hasher = hashlib.sha256()
        hasher.update(normalized_method.encode("utf-8"))
        hasher.update(b":")
        hasher.update(normalized_path.encode("utf-8"))
        hasher.update(b":")
        hasher.update(canonical_content)
        return hasher.hexdigest()

    async def execute_idempotent_operation(
        self,
        *,
        user_id: int,
        workspace_id: int,
        idempotency_key: str | None,
        operation: str,
        fingerprint: str,
        operation_func: Callable[[int | None], Coroutine[Any, Any, tuple[int, T]]],
    ) -> tuple[int, T]:
        """执行幂等操作：若未传 key 则直接在事务中执行；若传 key 则单事务先插入占位、执行并更新为 completed。"""

        # 若未提供 Idempotency-Key，直接执行并提交事务
        if not idempotency_key:
            status_code, result = await operation_func(None)
            await self.session.commit()
            return status_code, result

        normalized_key = str(idempotency_key).strip()
        expires_at = utc_now() + timedelta(days=self.settings.idempotency_retention_days)

        # 尝试在当前事务插入 in_progress 占位记录
        record_id: int | None = None
        collision_detected = False

        try:
            record = ApiIdempotencyRecord(
                user_id=user_id,
                workspace_id=workspace_id,
                idempotency_key=normalized_key,
                operation=operation,
                request_fingerprint=fingerprint,
                status="in_progress",
                expires_at=expires_at,
                created_at=utc_now(),
            )
            self.session.add(record)
            await self.session.flush()
            record_id = record.id
        except IntegrityError as exc:
            await self.session.rollback()
            collision_detected = True
            logger.info("幂等占位插入唯一约束冲突: %s", exc)

        # 若发生唯一冲突，重查已有记录并处理重放或并发冲突
        if collision_detected:
            return await self._handle_existing_record(
                user_id=user_id,
                workspace_id=workspace_id,
                idempotency_key=normalized_key,
                operation=operation,
                fingerprint=fingerprint,
                operation_func=operation_func,
            )

        # 成功插入占位，在同一事务内执行核心业务
        try:
            status_code, result = await operation_func(record_id)

            # 更新占位为 completed 并保存响应
            record.status = "completed"
            record.status_code = status_code
            if isinstance(result, (dict, list)):
                record.response_body = result
            elif hasattr(result, "model_dump"):
                record.response_body = result.model_dump(mode="json")
            else:
                record.response_body = {"result": str(result)}

            await self.session.commit()
            return status_code, result
        except Exception:
            await self.session.rollback()
            raise

    async def _handle_existing_record(
        self,
        *,
        user_id: int,
        workspace_id: int,
        idempotency_key: str,
        operation: str,
        fingerprint: str,
        operation_func: Any,
    ) -> tuple[int, Any]:
        """处理已有幂等记录的重放或冲突；若已过期则复用并重写。"""

        now = utc_now()

        # SQLite 锁重试读取
        for delay in SQLITE_BACKOFF_DELAYS:
            try:
                stmt = (
                    select(ApiIdempotencyRecord)
                    .where(ApiIdempotencyRecord.user_id == user_id)
                    .where(ApiIdempotencyRecord.workspace_id == workspace_id)
                    .where(ApiIdempotencyRecord.idempotency_key == idempotency_key)
                    .where(ApiIdempotencyRecord.operation == operation)
                )
                existing = await self.session.scalar(stmt)
                if existing is not None:
                    break
            except OperationalError:
                await asyncio.sleep(delay)
        else:
            existing = await self.session.scalar(stmt)

        if existing is None:
            raise AppException(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                detail="并发请求冲突，请重试。",
            )

        # 检查是否过期，若已过期则复用更新为 in_progress 并重新执行
        if existing.expires_at is not None and normalize_utc(existing.expires_at) <= now:
            logger.info("幂等记录已过期，复用并重写 (key: %s)", idempotency_key)
            existing.request_fingerprint = fingerprint
            existing.status = "in_progress"
            existing.expires_at = now + timedelta(days=self.settings.idempotency_retention_days)
            existing.created_at = now
            existing.response_body = None
            existing.status_code = None
            await self.session.flush()

            try:
                status_code, result = await operation_func(existing.id)
                existing.status = "completed"
                existing.status_code = status_code
                if isinstance(result, (dict, list)):
                    existing.response_body = result
                elif hasattr(result, "model_dump"):
                    existing.response_body = result.model_dump(mode="json")
                else:
                    existing.response_body = {"result": str(result)}
                await self.session.commit()
                return status_code, result
            except Exception:
                await self.session.rollback()
                raise

        # 校验请求指纹一致性
        if existing.request_fingerprint != fingerprint:
            raise AppException(
                status_code=409,
                code="IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD",
                detail="相同的 Idempotency-Key 已用于不同参数或路径的请求，禁止复用。",
            )

        # 校验是否正在执行
        if existing.status == "in_progress":
            raise AppException(
                status_code=409,
                code="CONCURRENT_MUTATION_IN_PROGRESS",
                detail="具有相同幂等键的写操作正在处理中，请稍后查询或等待完成。",
            )

        # 重放已完成的成功响应
        return existing.status_code or 200, existing.response_body

    @classmethod
    async def clean_expired_records(cls) -> int:
        """周期性清理超过保留期的过期幂等记录。"""

        now = utc_now()
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = delete(ApiIdempotencyRecord).where(ApiIdempotencyRecord.expires_at <= now)
            res = await session.execute(stmt)
            await session.commit()
            return res.rowcount or 0
