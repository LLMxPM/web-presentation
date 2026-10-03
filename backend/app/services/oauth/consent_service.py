"""文件功能：绑定平台会话创建确认请求，以一次性 CAS 原子消费并保存用户批准的授权码。"""

import secrets
from collections.abc import Callable
from datetime import timedelta
from urllib.parse import parse_qsl
from uuid import uuid4

from authlib.oauth2.rfc6749.errors import InvalidRequestError, OAuth2Error
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.external_operations import OPERATION_REGISTRY
from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthAuthorizationCode
from app.models.oauth_grant import OAuthConsentRequest, OAuthGrant
from app.repositories.oauth_consent_repository import (
    consent_workspaces,
    register_chatgpt_client,
    require_consent_session,
)
from app.repositories.oauth_repository import load_client
from app.schemas.oauth_account import (
    OAuthConsentDecision,
    OAuthConsentView,
    OAuthScopeChoice,
)
from app.services.oauth.chatgpt_client import fetch_chatgpt_client
from app.services.oauth.persistence import add_audit
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.protocol import McpAuthorizationServer, credential_digest
from app.services.oauth.request import ProtocolRequest


def authorization_request(query: str, policy: OAuthPolicy) -> ProtocolRequest:
    """保留查询重复项并限制参数种类，不接收 request_uri、OIDC 或任意请求扩展。"""
    if len(query) > 8192:
        raise InvalidRequestError("Authorization request is too large.")
    try:
        pairs = parse_qsl(query, keep_blank_values=True, max_num_fields=32)
    except ValueError as error:
        raise InvalidRequestError() from error
    request = ProtocolRequest(method="GET", uri=policy.issuer + "/oauth/authorize", pairs=pairs)
    request.payload.ensure_single_values()
    allowed = {"client_id", "redirect_uri", "response_type", "scope", "state", "resource", "code_challenge", "code_challenge_method"}
    if set(request.args) - allowed:
        raise InvalidRequestError("Unsupported authorization parameter.")
    return request


class OAuthConsentService:
    """只有已认证的 Cookie 用户可以创建/确认请求，不持有可变全局协议状态。"""

    def __init__(self, session_factory: Callable[[], AsyncSession], policy: OAuthPolicy) -> None:
        """注入独立事务工厂及显式发行策略。"""
        self.session_factory = session_factory
        self.policy = policy

    async def validate(self, query: str):
        """读取受限 CIMD 后用 Authlib 校验 PKCE、回调、resource 与 Scope。"""
        request = authorization_request(query, self.policy)
        client = await fetch_chatgpt_client(request.payload.client_id or "", self.policy)
        server = McpAuthorizationServer(client=client, issuer=self.policy.issuer)
        server.get_consent_grant(request)
        return request, client

    async def begin(self, *, query: str, user_id: int, session_id: int) -> OAuthConsentView:
        """确认前保存不可变请求和 nonce 摘要；网络读取不占用数据库事务。"""
        request, client = await self.validate(query)
        now = utc_now()
        csrf = secrets.token_urlsafe(48)
        pending = {
            "request_id": uuid4().hex, "user_id": user_id, "session_id": session_id,
            "client_id": client.client_id, "redirect_uri": request.args["redirect_uri"],
            "resource": self.policy.mcp_resource, "scopes": sorted(set(request.args["scope"].split())),
            "state": request.args.get("state"), "code_challenge": request.args["code_challenge"],
            "code_challenge_method": "S256", "csrf_hash": credential_digest(csrf),
            "created_at": now, "expires_at": now + timedelta(seconds=self.policy.consent_ttl_seconds),
        }

        async def persist(session: AsyncSession) -> OAuthConsentView:
            """先写客户端锁再复核会话，插入只保存摘要的确认请求。"""
            await register_chatgpt_client(session, client)
            await require_consent_session(session, user_id, session_id, now)
            outstanding = await session.scalar(select(func.count()).select_from(OAuthConsentRequest).where(
                OAuthConsentRequest.user_id == user_id, OAuthConsentRequest.consumed_at.is_(None),
                OAuthConsentRequest.expires_at > now,
            ))
            if outstanding >= 10:
                raise AppException(429, "OAUTH_CONSENT_LIMIT", "待确认授权过多，请完成已有授权或稍后重试。")
            workspaces = await consent_workspaces(session, user_id)
            session.add(OAuthConsentRequest(**pending))
            await session.commit()
            return OAuthConsentView(
                request_id=pending["request_id"], csrf_token=csrf, client_name="ChatGPT",
                resource=self.policy.mcp_resource, workspaces=workspaces,
                expires_at=pending["expires_at"], scopes=[OAuthScopeChoice(
                    scope=scope, operations=sorted({spec.description for spec in OPERATION_REGISTRY.values() if scope in spec.scopes})
                ) for scope in pending["scopes"]],
            )

        async def write():
            """统一由数据库适配层处理写冲突。"""
            return await run_with_write_retry(persist, session_factory=self.session_factory, backoff_delays=(0.01, 0.03, 0.08))

        try:
            return await write()
        except IntegrityError:
            # 首次不同用户同时登记同一 CIMD 的唯一键竞态；只在确有该行时重做整批事务。
            async with self.session_factory() as session:
                if await load_client(session, client.client_id, self.policy) is None:
                    raise
            return await write()

    async def decide(self, *, request_id: str, user_id: int, session_id: int, decision: OAuthConsentDecision) -> str:
        """一次性消费确认请求；批准的 Grant/Code/审计必须同事务提交后才交付回调。"""
        async def persist(session: AsyncSession) -> str:
            """CAS 是首条数据库操作；错误 nonce、过期、跨用户和重放均不能消费。"""
            now = utc_now()
            consumed = await session.execute(update(OAuthConsentRequest).where(
                OAuthConsentRequest.request_id == request_id,
                OAuthConsentRequest.user_id == user_id, OAuthConsentRequest.session_id == session_id,
                OAuthConsentRequest.csrf_hash == credential_digest(decision.csrf_token),
                OAuthConsentRequest.expires_at > now, OAuthConsentRequest.consumed_at.is_(None),
            ).values(consumed_at=now).execution_options(synchronize_session=False))
            if consumed.rowcount != 1:
                raise AppException(403, "OAUTH_CONSENT_INVALID", "授权请求已失效或已使用，请从 ChatGPT 重新连接。")
            pending = await session.get(OAuthConsentRequest, request_id, populate_existing=True)
            await require_consent_session(session, user_id, session_id, now)
            client = await load_client(session, pending.client_id, self.policy)
            if client is None or pending.resource != self.policy.mcp_resource:
                raise AppException(403, "OAUTH_CLIENT_INVALID", "客户端授权配置已失效。")
            scopes = set(decision.scopes) if decision.approved else set(pending.scopes)
            workspace_ids = set(decision.workspace_ids)
            if decision.approved:
                choices = await consent_workspaces(session, user_id)
                if (
                    not scopes or not scopes <= set(pending.scopes)
                    or not workspace_ids or not workspace_ids <= {item.id for item in choices}
                    or len(workspace_ids) != len(decision.workspace_ids)
                    or len(scopes) != len(decision.scopes)
                ):
                    raise AppException(403, "OAUTH_CONSENT_SCOPE_INVALID", "请选择请求范围内的权限和当前可访问工作空间。")
            data = {
                "client_id": pending.client_id, "redirect_uri": pending.redirect_uri,
                "response_type": "code", "resource": pending.resource,
                "scope": " ".join(sorted(scopes)), "code_challenge": pending.code_challenge,
                "code_challenge_method": pending.code_challenge_method,
            }
            if pending.state is not None:
                data["state"] = pending.state
            request = ProtocolRequest(method="GET", uri=self.policy.issuer + "/oauth/authorize", pairs=data.items())
            server = McpAuthorizationServer(client=client, issuer=self.policy.issuer, now=now)
            try:
                grant = server.get_consent_grant(request, end_user=user_id)
                response = server.create_authorization_response(request, grant_user=user_id if decision.approved else None, grant=grant)
            except OAuth2Error as error:
                raise AppException(403, "OAUTH_CONSENT_INVALID", "授权请求校验失败，请重新连接。") from error
            if response.location is None:
                raise AppException(403, "OAUTH_CONSENT_INVALID", "授权回调无效，请重新连接。")
            if decision.approved:
                if server.pending_code is None:
                    raise AppException(403, "OAUTH_CONSENT_INVALID", "无法发行授权码，请重新连接。")
                granted = OAuthGrant(
                    grant_id=uuid4().hex, user_id=user_id, client_id=pending.client_id,
                    issuer=self.policy.issuer, resource=pending.resource,
                    workspace_ids=sorted(workspace_ids), scopes=sorted(scopes),
                )
                session.add(granted)
                await session.flush()
                session.add(OAuthAuthorizationCode(
                    code_hash=credential_digest(server.pending_code), grant_id=granted.grant_id,
                    redirect_uri=pending.redirect_uri, scopes=sorted(scopes),
                    code_challenge=pending.code_challenge, code_challenge_method="S256",
                    created_at=now, expires_at=now + timedelta(seconds=self.policy.code_ttl_seconds),
                ))
                add_audit(session, event="consent_approved", grant=granted, now=now)
            else:
                session.add(OAuthAuditEvent(
                    event_id=uuid4().hex, event="consent_denied", user_id=user_id,
                    client_id=pending.client_id, created_at=now,
                ))
            await session.commit()
            return response.location

        return await run_with_write_retry(persist, session_factory=self.session_factory, backoff_delays=(0.01, 0.03, 0.08))
