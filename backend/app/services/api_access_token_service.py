"""文件功能：管理个人访问令牌（PAT）的创建、列表、吊销与 Bearer 鉴权校验。"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import normalize_utc, utc_now
from app.db.session import get_session_factory
from app.models.api_access_token import (
    ApiAccessToken,
    ApiAccessTokenScope,
    ApiAccessTokenWorkspace,
)
from app.models.enums import RecordStatus
from app.models.workspace import WorkspaceMember
from app.schemas.api_access_token import (
    ApiAccessTokenCreateRequest,
    ApiAccessTokenCreateResponse,
    ApiAccessTokenItem,
    ApiAccessTokenListResponse,
)
from app.services.pat_security_service import PatAuditService, PatRateLimitService
from app.services.redis_runtime_client import get_redis_runtime_client

logger = logging.getLogger(__name__)

PAT_FORMAT_RE = re.compile(r"^wp_pat_([a-zA-Z0-9]{16})\.([a-fA-F0-9]{64})$")
PAT_LAST_USED_THROTTLE_SECONDS = 300  # 5 分钟 Redis 节流


class ApiAccessTokenService:
    """个人访问令牌服务，负责 Web 端单向管理与 External API 鉴权。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def create_token(
        self,
        *,
        user_id: int,
        payload: ApiAccessTokenCreateRequest,
        ip: str | None = None,
    ) -> ApiAccessTokenCreateResponse:
        """在 Web 端为当前用户创建新 PAT，仅在创建响应中返回一次明文 Token。"""

        # 1. 活跃数量上限检查 (25)
        active_count_stmt = (
            select(ApiAccessToken)
            .where(ApiAccessToken.user_id == user_id)
            .where(ApiAccessToken.revoked_at.is_(None))
            .where(or_(ApiAccessToken.expires_at.is_(None), ApiAccessToken.expires_at > utc_now()))
        )
        active_tokens = (await self.session.scalars(active_count_stmt)).all()
        if len(active_tokens) >= self.settings.pat_max_active_tokens:
            raise AppException(
                status_code=409,
                code="PAT_MAX_ACTIVE_LIMIT_REACHED",
                detail=f"活跃访问令牌已达上限 ({self.settings.pat_max_active_tokens} 个)，请先吊销旧令牌后再创建。",
            )

        # 2. 授权工作空间归属校验（用户必须是目标空间的 active member）
        for ws_id in payload.workspace_ids:
            member = await self.session.scalar(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == ws_id)
                .where(WorkspaceMember.user_id == user_id)
                .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
            )
            if member is None:
                raise AppException(
                    status_code=403,
                    code="PERMISSION_DENIED",
                    detail=f"无权授权未加入或已被禁用的工作空间 (ID: {ws_id})。",
                )

        # 3. 生成安全密钥 (256-bit secret, 16 字符 public_id)
        public_id = secrets.token_hex(8)  # 16 字符
        secret_hex = secrets.token_hex(32)  # 64 字符十六进制 (256 bits)
        plain_token = f"wp_pat_{public_id}.{secret_hex}"
        token_hash = hashlib.sha256(plain_token.encode("utf-8")).hexdigest()

        expires_at = None
        if payload.expires_in_days is not None:
            ttl_days = min(payload.expires_in_days, self.settings.pat_max_ttl_days)
            expires_at = utc_now() + timedelta(days=ttl_days)

        token_model = ApiAccessToken(
            user_id=user_id,
            name=payload.name,
            token_public_id=public_id,
            token_hash=token_hash,
            expires_at=expires_at,
            all_workspaces=payload.all_workspaces,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(token_model)
        await self.session.flush()

        for ws_id in payload.workspace_ids:
            self.session.add(
                ApiAccessTokenWorkspace(token_id=token_model.id, workspace_id=ws_id)
            )
        for scope_str in payload.scopes:
            self.session.add(
                ApiAccessTokenScope(token_id=token_model.id, scope=scope_str)
            )

        await self.session.commit()
        PatAuditService.log_token_created(
            user_id=user_id,
            token_id=token_model.id,
            public_id=public_id,
            name=payload.name,
            ip=ip,
        )

        return ApiAccessTokenCreateResponse(
            id=token_model.id,
            name=token_model.name,
            token_public_id=public_id,
            token=plain_token,
            expires_at=token_model.expires_at,
            all_workspaces=token_model.all_workspaces,
            workspace_ids=payload.workspace_ids,
            scopes=payload.scopes,
            created_at=token_model.created_at,
        )

    async def list_tokens(self, *, user_id: int) -> ApiAccessTokenListResponse:
        """列出当前用户的所有访问令牌（支持展示活跃与已吊销历史，脱敏展示）。"""

        stmt = (
            select(ApiAccessToken)
            .options(
                selectinload(ApiAccessToken.workspaces),
                selectinload(ApiAccessToken.scopes),
            )
            .where(ApiAccessToken.user_id == user_id)
            .order_by(ApiAccessToken.created_at.desc())
        )
        tokens = (await self.session.scalars(stmt)).all()
        now = utc_now()

        items = [
            ApiAccessTokenItem(
                id=t.id,
                name=t.name,
                token_public_id=t.token_public_id,
                token_masked=f"wp_pat_{t.token_public_id[:8]}****",
                expires_at=t.expires_at,
                revoked_at=t.revoked_at,
                last_used_at=t.last_used_at,
                last_used_ip=t.last_used_ip,
                is_active=(t.revoked_at is None and (t.expires_at is None or normalize_utc(t.expires_at) > now)),
                all_workspaces=t.all_workspaces,
                workspace_ids=[w.workspace_id for w in t.workspaces],
                scopes=[s.scope for s in t.scopes],
                created_at=t.created_at,
            )
            for t in tokens
        ]
        return ApiAccessTokenListResponse(items=items, total=len(items))

    async def revoke_token(self, *, user_id: int, token_id: int, ip: str | None = None) -> None:
        """吊销当前用户的指定 PAT（即刻生效，幂等返回）。"""

        token = await self.session.get(ApiAccessToken, token_id)
        if token is None or token.user_id != user_id:
            raise AppException(
                status_code=404,
                code="OBJECT_NOT_FOUND",
                detail="访问令牌不存在。",
            )

        if token.revoked_at is not None:
            return

        token.revoked_at = utc_now()
        token.updated_at = utc_now()
        await self.session.commit()

        PatAuditService.log_token_revoked(
            user_id=user_id,
            token_id=token.id,
            public_id=token.token_public_id,
            ip=ip,
        )

    async def authenticate_pat(self, raw_token: str, ip: str | None = None) -> ApiAccessToken:
        """校验 Bearer PAT 合法性，执行防暴破限速、恒定时间哈希比对与 Redis 节流更新 last_used_at。"""

        # 1. 格式预校验
        match = PAT_FORMAT_RE.match(raw_token.strip())
        if not match:
            PatRateLimitService.record_auth_failure(ip, None)
            PatAuditService.log_auth_failure(public_id=None, reason="INVALID_FORMAT", ip=ip)
            raise AppException(
                status_code=401,
                code="UNAUTHENTICATED",
                detail="访问令牌格式错误。",
            )

        public_id = match.group(1)

        # 2. 封禁桶与请求速率限速
        PatRateLimitService.check_ip_rate_limit(ip)
        PatRateLimitService.check_auth_failure_rate_limit(ip, public_id)

        # 3. 按 public_id 检索数据库行
        stmt = (
            select(ApiAccessToken)
            .options(
                selectinload(ApiAccessToken.user),
                selectinload(ApiAccessToken.workspaces),
                selectinload(ApiAccessToken.scopes),
            )
            .where(ApiAccessToken.token_public_id == public_id)
        )
        token = await self.session.scalar(stmt)

        # 4. 恒定时间哈希比对
        expected_hash = token.token_hash if token is not None else "0" * 64
        incoming_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
        is_valid_hash = hmac.compare_digest(incoming_hash, expected_hash)

        if token is None or not is_valid_hash:
            PatRateLimitService.record_auth_failure(ip, public_id)
            PatAuditService.log_auth_failure(public_id=public_id, reason="HASH_MISMATCH", ip=ip)
            raise AppException(
                status_code=401,
                code="UNAUTHENTICATED",
                detail="访问令牌无效或已过期。",
            )

        # 5. 校验吊销与过期
        now = utc_now()
        if token.revoked_at is not None or (token.expires_at is not None and normalize_utc(token.expires_at) <= now):
            PatRateLimitService.record_auth_failure(ip, public_id)
            PatAuditService.log_auth_failure(public_id=public_id, reason="REVOKED_OR_EXPIRED", ip=ip)
            raise AppException(
                status_code=401,
                code="UNAUTHENTICATED",
                detail="访问令牌已被吊销或已过期。",
            )

        # 6. 校验所属用户状态
        if token.user.status != RecordStatus.ACTIVE.value:
            PatAuditService.log_auth_failure(public_id=public_id, reason="USER_INACTIVE", ip=ip)
            raise AppException(
                status_code=403,
                code="PERMISSION_DENIED",
                detail="用户账号已被禁用或已删除。",
            )

        # 7. Redis 5 分钟节流更新 last_used_at；等待独立短事务收敛，避免遗留后台任务。
        await self._update_last_used(token.id, ip)

        return token

    async def _update_last_used(self, token_id: int, ip: str | None) -> None:
        """通过 Redis 节流在独立短事务中更新最后使用信息，失败时不阻断鉴权。"""

        try:
            redis = get_redis_runtime_client()
            throttle_key = redis.key(f"pat:last_used_throttle:{token_id}")
            is_new = redis.client.set(throttle_key, "1", ex=PAT_LAST_USED_THROTTLE_SECONDS, nx=True)
            if not is_new:
                return
        except Exception as exc:
            logger.warning("Redis 节流检查异常: %s", exc)

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                await session.execute(
                    update(ApiAccessToken)
                    .where(ApiAccessToken.id == token_id)
                    .values(last_used_at=utc_now(), last_used_ip=ip)
                )
                await session.commit()
        except Exception as err:
            logger.warning("更新 PAT last_used_at 失败: %s", err)
