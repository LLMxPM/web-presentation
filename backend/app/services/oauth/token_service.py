"""文件功能：把 Authlib 发行意图与异步 SQLAlchemy 事务接合，提交成功才交付 Token。"""

from collections.abc import Callable

from authlib.oauth2.rfc6749.errors import (
    InvalidClientError,
    InvalidGrantError,
    OAuth2Error,
)
from authlib.oauth2.rfc6749.util import extract_basic_authorization
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.oauth_grant import OAuthGrant
from app.repositories.oauth_repository import load_client, load_credential
from app.services.oauth.audit_logging import commit_audit_events
from app.services.oauth.persistence import (
    add_audit,
    lock_grant,
    persist_issuance,
    revoke_locked_grant,
)
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.protocol import (
    McpAuthorizationServer,
    ProtocolResponse,
    credential_digest,
)
from app.services.oauth.request import ProtocolRequest


def request_client_id(request: ProtocolRequest) -> str | None:
    """复用 Authlib Basic 解析做查询定位；实际认证仍交给协议核。"""
    basic_id, _ = extract_basic_authorization(request.headers)
    body_id = request.payload.client_id
    if basic_id and body_id and basic_id != body_id:
        raise InvalidClientError()
    return basic_id or body_id


class OAuthTokenService:
    """每请求使用独立 Session，协议对象不跨请求或跨副本共享。"""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], policy: OAuthPolicy
    ) -> None:
        """接收应用数据库会话工厂和显式信任配置，便于隔离数据库演练。"""
        self.session_factory = session_factory
        self.policy = policy

    async def _prepare(
        self, session: AsyncSession, request: ProtocolRequest
    ) -> McpAuthorizationServer:
        """从实时数据库预读快照，不在 Authlib 的同步钩子里执行异步 IO。"""
        now = utc_now()
        client_id = request_client_id(request)
        client = await load_client(session, client_id, self.policy)
        raw = (
            request.form.get("code")
            if request.payload.grant_type == "authorization_code"
            else request.form.get("refresh_token")
        )
        credential = await load_credential(
            session,
            kind=request.payload.grant_type,
            digest=credential_digest(raw or ""),
            client_id=client_id,
            policy=self.policy,
            now=now,
        )
        return McpAuthorizationServer(
            client=client,
            credential=credential,
            now=now,
            access_ttl_seconds=self.policy.access_ttl_seconds,
        )

    async def token_response(self, request: ProtocolRequest) -> ProtocolResponse:
        """先验证协议，再锁授权并重读；并发失败、撤销或提交失败绝不返回暂存 Token。"""
        fallback = McpAuthorizationServer(client=None)
        try:
            request.payload.ensure_single_values()
            async with self.session_factory() as session:
                server = await self._prepare(session, request)
            response = server.token_response(request)
        except OAuth2Error as error:
            return fallback.handle_error_response(request, error)
        credential = server.credential_snapshot
        if credential is None or (
            response.status_code != 200 and server.replayed_refresh_hash is None
        ):
            return response
        grant_id = credential.grant_id

        async def persist(session: AsyncSession) -> ProtocolResponse:
            """写操作先取得真实锁，再复核协议、消费状态和所有权限并原子提交。"""
            if not await lock_grant(session, grant_id, self.policy):
                await session.rollback()
                return fallback.handle_error_response(request, InvalidGrantError())
            current = await self._prepare(session, request)
            current_response = current.token_response(request)
            grant = await session.get(OAuthGrant, grant_id, populate_existing=True)
            if current.replayed_refresh_hash and grant is not None:
                audit = await revoke_locked_grant(
                    session, grant, now=current.now, reason="refresh_replay"
                )
                await commit_audit_events(session, [audit])
                return current_response
            if (
                current_response.status_code != 200
                or current.credential_snapshot is None
                or current.pending_token is None
                or grant is None
            ):
                await session.rollback()
                return current_response
            saved = await persist_issuance(
                session,
                credential=current.credential_snapshot,
                token=current.pending_token,
                policy=self.policy,
                now=current.now,
            )
            if not saved:
                await session.rollback()
                return fallback.handle_error_response(request, InvalidGrantError())
            audit = add_audit(
                session,
                event="refresh_rotated"
                if current.credential_snapshot.family_id
                else "code_consumed",
                grant=grant,
                now=current.now,
            )
            await commit_audit_events(session, [audit])
            return current_response

        return await run_with_write_retry(
            persist,
            session_factory=self.session_factory,
            backoff_delays=(0.01, 0.03, 0.08),
        )
