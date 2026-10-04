"""文件功能：分批回收 OAuth 终态记录，保留活跃刷新链的重放证据与凭证来源外键。"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthAuthorizationCode, OAuthToken
from app.models.oauth_grant import OAuthConsentRequest, OAuthGrant, OAuthRefreshFamily
from app.services.oauth.policy import (
    MAX_AUDIT_RETENTION_SECONDS,
    MAX_CREDENTIAL_RETENTION_SECONDS,
)

logger = logging.getLogger(__name__)


class OAuthCleanupService:
    """清理只删除超过保留期的记录；注册、Grant 历史和业务任务均独立保留。"""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], *, batch_size: int = 200
    ):
        """每类最多删除 batch_size 条，单轮有界；按冻结的 7/30 天保留策略执行。"""
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise ValueError("清理 batch_size 须为 1～1000 的整数。")
        self.session_factory = session_factory
        self.batch_size = batch_size

    async def sweep(
        self, *, dry_run: bool = False, now: datetime | None = None
    ) -> dict[str, int]:
        """预检只返回当前批次数量；执行按子到父回收，在单事务提交后返回实际数量。"""
        now = now or utc_now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("清理时刻必须含时区。")
        cutoff = now - timedelta(seconds=MAX_CREDENTIAL_RETENTION_SECONDS)
        audit_cutoff = now - timedelta(seconds=MAX_AUDIT_RETENTION_SECONDS)

        async def persist(session: AsyncSession) -> dict[str, int]:
            """删除语句内保留资格条件，多个清理进程也不会删除活跃凭证或来源引用。"""
            counts = {}
            for model, key, condition, label in (
                (
                    OAuthConsentRequest,
                    OAuthConsentRequest.request_id,
                    OAuthConsentRequest.expires_at <= cutoff,
                    "consents",
                ),
                (
                    OAuthAuthorizationCode,
                    OAuthAuthorizationCode.code_hash,
                    OAuthAuthorizationCode.expires_at <= cutoff,
                    "codes",
                ),
            ):
                counts[label] = await self._batch(
                    session, model, key, condition, dry_run
                )
            for kind in ("delegated", "access", "refresh"):
                counts[kind] = await self._batch(
                    session,
                    OAuthToken,
                    OAuthToken.token_id,
                    self._token_condition(kind, cutoff),
                    dry_run,
                )
            counts["families"] = await self._batch(
                session,
                OAuthRefreshFamily,
                OAuthRefreshFamily.family_id,
                or_(
                    OAuthRefreshFamily.expires_at <= cutoff,
                    OAuthRefreshFamily.revoked_at <= cutoff,
                )
                & ~exists(
                    select(OAuthToken.token_id).where(
                        OAuthToken.family_id == OAuthRefreshFamily.family_id,
                    )
                ),
                dry_run,
            )
            counts["audits"] = await self._batch(
                session,
                OAuthAuditEvent,
                OAuthAuditEvent.event_id,
                OAuthAuditEvent.created_at <= audit_cutoff,
                dry_run,
            )
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
            return counts

        return await run_with_write_retry(
            persist,
            session_factory=self.session_factory,
            backoff_delays=(0.02, 0.05, 0.1),
        )

    @staticmethod
    def _token_condition(kind: str, cutoff: datetime):
        """轮换 refresh 只有家族终止后才可删；所有 Token 必须已终止且没有后代引用。"""
        family_terminal = exists(
            select(OAuthRefreshFamily.family_id).where(
                OAuthRefreshFamily.family_id == OAuthToken.family_id,
                or_(
                    OAuthRefreshFamily.expires_at <= cutoff,
                    OAuthRefreshFamily.revoked_at <= cutoff,
                ),
            )
        )
        grant_terminal = exists(
            select(OAuthGrant.grant_id).where(
                OAuthGrant.grant_id == OAuthToken.grant_id,
                OAuthGrant.revoked_at <= cutoff,
            )
        )
        terminal = or_(
            OAuthToken.expires_at <= cutoff,
            OAuthToken.revoked_at <= cutoff,
            grant_terminal,
        )
        if kind == "refresh":
            terminal = family_terminal | grant_terminal
        child = aliased(OAuthToken)
        referenced = exists(
            select(child.token_id).where(
                or_(
                    child.parent_token_id == OAuthToken.token_id,
                    child.source_token_id == OAuthToken.token_id,
                )
            )
        )
        return (OAuthToken.kind == kind) & terminal & ~referenced

    async def _batch(
        self, session: AsyncSession, model, key, condition, dry_run: bool
    ) -> int:
        """在 SQL 内限定有序批次；RETURNING 计数避免方言 rowcount 差异和无界 ORM 加载。"""
        candidates = select(key).where(condition).order_by(key).limit(self.batch_size)
        if dry_run:
            return len((await session.scalars(candidates)).all())
        removed = await session.scalars(
            delete(model).where(key.in_(candidates)).returning(key)
        )
        return len(removed.all())


async def run_oauth_cleanup_loop(session_factory: Callable[[], AsyncSession]) -> None:
    """每五分钟清理一个有界批次；关闭 OAuth 后继续回收遗留数据，取消时释放 Session。"""
    service = OAuthCleanupService(session_factory)
    while True:
        try:
            counts = await service.sweep()
            if any(counts.values()):
                logger.info(
                    "OAuth 过期记录已清理。",
                    extra={"event": "oauth.cleanup", "counts": counts},
                )
        except Exception:  # noqa: BLE001 - 单轮失败不能让清理任务退出
            # 不记录数据库异常参数，避免 Token 摘要和连接凭证进入日志。
            logger.error(
                "OAuth 清理失败，下个周期重试。",
                extra={"event": "oauth.cleanup.failed"},
            )
        await asyncio.sleep(300)
