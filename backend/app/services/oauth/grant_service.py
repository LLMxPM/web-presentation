"""文件功能：提供平台用户对自己 OAuth Grant 的幂等撤销，与 Token 发行使用相同围栏。"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.oauth_grant import OAuthGrant
from app.services.oauth.audit_logging import commit_audit_events
from app.services.oauth.persistence import lock_grant, revoke_locked_grant
from app.services.oauth.policy import OAuthPolicy


class OAuthGrantService:
    """只根据平台已认证用户管理授权，不接受客户端声明的用户身份。"""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], policy: OAuthPolicy
    ) -> None:
        """复用根 workspace 数据库工厂，显式传入发行边界。"""
        self.session_factory = session_factory
        self.policy = policy

    async def revoke(self, *, user_id: int, grant_id: str) -> bool:
        """撤销用户自己的授权；未知或他人 ID 同为 False，已撤销返回 True。"""

        async def operation(session: AsyncSession) -> bool:
            """先结束定位读事务，再取得授权写锁，避免读快照升级为写锁。"""
            from app.db.tx import commit_end_read

            exists = await session.scalar(
                select(OAuthGrant.grant_id).where(
                    OAuthGrant.grant_id == grant_id,
                    OAuthGrant.user_id == user_id,
                    OAuthGrant.issuer == self.policy.issuer,
                    OAuthGrant.resource == self.policy.mcp_resource,
                )
            )
            await commit_end_read(session)
            if exists is None:
                return False
            locked = await lock_grant(session, grant_id, self.policy)
            grant = await session.get(OAuthGrant, grant_id, populate_existing=True)
            if grant is None or grant.user_id != user_id:
                await session.rollback()
                return False
            if locked:
                audit = await revoke_locked_grant(
                    session, grant, now=utc_now(), reason="user_revoked"
                )
                await commit_audit_events(session, [audit])
            else:
                await session.rollback()
            return True

        return await run_with_write_retry(
            operation,
            session_factory=self.session_factory,
            backoff_delays=(0.01, 0.03, 0.08),
        )
