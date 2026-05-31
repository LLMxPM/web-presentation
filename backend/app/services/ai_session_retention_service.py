"""文件功能：定期删除长期未更新的 Agno 会话，控制 AI 历史存储增长。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import AppSettings


logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AiSessionRetentionStats:
    """记录一次 AI 会话清理的结果，便于日志和测试断言。"""

    cutoff_timestamp: int
    scanned_sessions: int
    deleted_sessions: int
    batches: int
    duration_ms: float


class AiSessionRetentionService:
    """按保留天数删除 Agno session 表中的整条历史会话。"""

    def __init__(
        self,
        *,
        agno_db: Any,
        retention_days: int,
        batch_size: int,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        """保存 Agno DB 与清理阈值；now_factory 仅供测试固定时间。"""

        if retention_days <= 0:
            raise ValueError("AI session 保留天数必须大于 0。")
        if batch_size <= 0:
            raise ValueError("AI session 清理批大小必须大于 0。")

        self._agno_db = agno_db
        self._retention_days = retention_days
        self._batch_size = batch_size
        self._now_factory = now_factory or (lambda: datetime.now(tz=UTC))

    async def cleanup_once(self) -> AiSessionRetentionStats:
        """执行一次清理：删除早于保留阈值的整条 Agno session。"""

        started_at = time.perf_counter()
        cutoff_timestamp = self._resolve_cutoff_timestamp()
        scanned_sessions = 0
        deleted_sessions = 0
        batches = 0
        page = 1

        while True:
            rows = await self._get_session_rows(page=page)
            if not rows:
                break

            batches += 1
            scanned_sessions += len(rows)
            expired_session_ids = [
                session_id
                for row in rows
                if _is_session_expired(row, cutoff_timestamp)
                for session_id in [_coerce_str(_row_get(row, "session_id"))]
                if session_id
            ]

            if expired_session_ids:
                await asyncio.to_thread(self._agno_db.delete_sessions, expired_session_ids)
                deleted_sessions += len(expired_session_ids)
                page = 1
                continue

            if _can_stop_by_updated_at_order(rows, cutoff_timestamp):
                break
            page += 1

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        stats = AiSessionRetentionStats(
            cutoff_timestamp=cutoff_timestamp,
            scanned_sessions=scanned_sessions,
            deleted_sessions=deleted_sessions,
            batches=batches,
            duration_ms=duration_ms,
        )
        logger.info(
            "AI 会话历史清理完成。",
            extra={
                "event": "ai.session_retention.completed",
                "cutoff_timestamp": stats.cutoff_timestamp,
                "scanned_sessions": stats.scanned_sessions,
                "deleted_sessions": stats.deleted_sessions,
                "batches": stats.batches,
                "duration_ms": stats.duration_ms,
            },
        )
        return stats

    def _resolve_cutoff_timestamp(self) -> int:
        """按当前时间和保留天数计算秒级清理阈值。"""

        now = self._now_factory()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return int((now - timedelta(days=self._retention_days)).timestamp())

    async def _get_session_rows(self, *, page: int) -> list[Any]:
        """按 updated_at 升序读取一页 Agno session 原始字典。"""

        result = await asyncio.to_thread(
            self._agno_db.get_sessions,
            session_type=None,
            user_id=None,
            component_id=None,
            session_name=None,
            start_timestamp=None,
            end_timestamp=None,
            limit=self._batch_size,
            page=page,
            sort_by="updated_at",
            sort_order="asc",
            deserialize=False,
        )
        if isinstance(result, tuple):
            result = result[0]
        if not isinstance(result, Sequence) or isinstance(result, (str, bytes, bytearray)):
            return []
        return list(result)


async def run_ai_session_retention_once_safely(service: AiSessionRetentionService) -> AiSessionRetentionStats | None:
    """执行一次清理并吞掉普通异常，避免清理失败影响应用运行。"""

    try:
        return await service.cleanup_once()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("AI 会话历史清理失败。", extra={"event": "ai.session_retention.failed"})
        return None


async def run_ai_session_retention_loop(service: AiSessionRetentionService, *, interval_seconds: int) -> None:
    """后台循环执行 AI session 清理；启动后先跑一次，再按间隔等待。"""

    if interval_seconds <= 0:
        return
    while True:
        await run_ai_session_retention_once_safely(service)
        await asyncio.sleep(interval_seconds)


def should_start_ai_session_retention_task(settings: AppSettings, agno_db: Any | None) -> bool:
    """判断当前运行配置是否需要启动 AI session 清理后台任务。"""

    return bool(settings.ai_enabled and agno_db is not None and settings.ai_session_cleanup_interval_seconds > 0)


def build_ai_session_retention_service(settings: AppSettings, agno_db: Any) -> AiSessionRetentionService:
    """按应用配置创建 AI session 清理服务。"""

    return AiSessionRetentionService(
        agno_db=agno_db,
        retention_days=settings.ai_session_retention_days,
        batch_size=settings.ai_session_cleanup_batch_size,
    )


def _is_session_expired(row: Any, cutoff_timestamp: int) -> bool:
    """判断 session 是否早于清理阈值；updated_at 缺失时使用 created_at。"""

    effective_timestamp = _session_effective_timestamp(row)
    return effective_timestamp is not None and effective_timestamp < cutoff_timestamp


def _session_effective_timestamp(row: Any) -> int | None:
    """读取用于清理判断的时间戳，优先 updated_at，缺失时兜底 created_at。"""

    updated_at = _coerce_timestamp(_row_get(row, "updated_at"))
    if updated_at is not None:
        return updated_at
    return _coerce_timestamp(_row_get(row, "created_at"))


def _can_stop_by_updated_at_order(rows: list[Any], cutoff_timestamp: int) -> bool:
    """在当前页没有删除项时，判断能否依赖 updated_at 排序提前停止扫描。"""

    for row in rows:
        updated_at = _coerce_timestamp(_row_get(row, "updated_at"))
        if updated_at is None or updated_at < cutoff_timestamp:
            return False
    return True


def _row_get(row: Any, key: str) -> Any:
    """兼容 dict、SQLAlchemy RowMapping 与测试替身读取字段。"""

    if isinstance(row, Mapping):
        return row.get(key)
    mapping = getattr(row, "_mapping", None)
    if isinstance(mapping, Mapping):
        return mapping.get(key)
    return getattr(row, key, None)


def _coerce_timestamp(value: Any) -> int | None:
    """把 Agno 原始时间字段归一为秒级 Unix 时间戳。"""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        resolved = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return int(resolved.timestamp())
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str | None:
    """把 session_id 等字段归一为非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None
