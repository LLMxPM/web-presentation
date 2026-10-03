"""文件功能：对接服务自省、客户端撤销及委托发行的异步事务，禁止提交前交付凭证。"""

from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

from authlib.oauth2.rfc6749.errors import InvalidGrantError, OAuth2Error
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.oauth_credential import OAuthToken
from app.models.oauth_grant import OAuthGrant
from app.repositories.oauth_repository import load_client
from app.repositories.oauth_resource_repository import load_service, load_token_snapshot
from app.services.oauth.persistence import add_audit, lock_grant, revoke_locked_grant
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.protocol import (
    McpAuthorizationServer,
    ProtocolResponse,
    credential_digest,
)
from app.services.oauth.request import ProtocolRequest
from app.services.oauth.token_service import request_client_id


class OAuthResourceService:
    """服务身份仅做自省和交换，用户客户端仅做自己的整链撤销。"""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], policy: OAuthPolicy
    ) -> None:
        """使用显式信任边界和独立 Session，不引入状态放行缓存。"""
        self.session_factory = session_factory
        self.policy = policy

    async def _prepare(
        self, session: AsyncSession, request: ProtocolRequest, endpoint: str
    ) -> McpAuthorizationServer:
        """自省/交换只加载服务注册，撤销只加载用户客户端注册。"""
        now = utc_now()
        identity = request_client_id(request)
        client = (
            await load_client(session, identity, self.policy)
            if endpoint == "revocation"
            else await load_service(session, identity, self.policy)
        )
        raw = (
            request.form.get("subject_token", "")
            if endpoint == "exchange"
            else request.form.get("token", "")
        )
        token = await load_token_snapshot(
            session,
            digest=credential_digest(raw),
            policy=self.policy,
            now=now,
            allowed_kinds=("access", "refresh")
            if endpoint == "revocation"
            else ("access",),
            require_live=endpoint != "revocation",
        )
        return McpAuthorizationServer(
            client=client,
            resource_token=token,
            now=now,
            delegated_ttl_seconds=self.policy.delegated_ttl_seconds,
        )

    @staticmethod
    def _respond(
        server: McpAuthorizationServer, endpoint: str, request: ProtocolRequest
    ) -> ProtocolResponse:
        """交由 Authlib 协议核生成标准成功/错误；成功仍是暂存结果。"""
        return (
            server.token_response(request)
            if endpoint == "exchange"
            else server.resource_response(endpoint, request)
        )

    async def response(
        self, endpoint: str, request: ProtocolRequest
    ) -> ProtocolResponse:
        """自省实时只读；交换/撤销经 Grant 围栏重新校验并提交后才返回。"""
        if endpoint not in {"exchange", "introspection", "revocation"}:
            raise ValueError("未知 OAuth 资源端点。")
        fallback = McpAuthorizationServer(client=None)
        try:
            request.payload.ensure_single_values()
            async with self.session_factory() as session:
                server = await self._prepare(session, request, endpoint)
            result = self._respond(server, endpoint, request)
        except OAuth2Error as error:
            return fallback.handle_error_response(request, error)
        if (
            endpoint == "introspection"
            or result.status_code != 200
            or (server.pending_token is None and server.pending_revocation is None)
        ):
            return result
        grant_id = server.resource_token.grant_id

        async def persist(session: AsyncSession) -> ProtocolResponse:
            """与消费/用户撤销共用数据库行锁，源权限变化不得越过提交边界。"""
            if not await lock_grant(session, grant_id, self.policy):
                await session.rollback()
                if endpoint == "revocation":
                    return result
                return fallback.handle_error_response(request, InvalidGrantError())
            current = await self._prepare(session, request, endpoint)
            response = self._respond(current, endpoint, request)
            grant = await session.get(OAuthGrant, grant_id, populate_existing=True)
            if response.status_code != 200 or grant is None:
                await session.rollback()
                return response
            if endpoint == "revocation":
                if current.pending_revocation:
                    await revoke_locked_grant(
                        session, grant, now=current.now, reason="client_revoked"
                    )
                else:
                    await session.rollback()
                    return response
            else:
                if current.pending_token is None or current.resource_token is None:
                    await session.rollback()
                    return fallback.handle_error_response(request, InvalidGrantError())
                token_id = uuid4().hex
                session.add(
                    OAuthToken(
                        token_id=token_id,
                        token_hash=credential_digest(
                            current.pending_token["access_token"]
                        ),
                        grant_id=grant_id,
                        kind="delegated",
                        audience=self.policy.api_audience,
                        scopes=sorted(current.pending_token["scope"].split()),
                        source_token_id=current.resource_token.token_id,
                        service_id=current.client_snapshot.client_id,
                        created_at=current.now,
                        expires_at=current.now
                        + timedelta(seconds=current.pending_token["expires_in"]),
                    )
                )
                add_audit(
                    session,
                    event="token_exchanged",
                    grant=grant,
                    now=current.now,
                    token_id=token_id,
                )
            await session.commit()
            return response

        return await run_with_write_retry(
            persist,
            session_factory=self.session_factory,
            backoff_delays=(0.01, 0.03, 0.08),
        )
