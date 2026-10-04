"""文件功能：查询 MCP 服务注册与各类 Token 的实时授权和来源链。"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_credential import OAuthToken
from app.models.oauth_grant import OAuthGrant, OAuthRefreshFamily
from app.models.oauth_registration import OAuthMcpService
from app.repositories.oauth_repository import load_live_grant
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.snapshots import ClientSnapshot
from app.services.oauth.token_snapshot import TokenSnapshot


async def lock_service(
    session: AsyncSession,
    service_id: str,
    policy: OAuthPolicy,
    *,
    require_active: bool = True,
) -> bool:
    """交换及运维先 UPDATE 同一服务行；停用/轮换不能越过发行事务的复核。"""
    predicates = [
        OAuthMcpService.service_id == service_id,
        OAuthMcpService.resource == policy.mcp_resource,
        OAuthMcpService.api_audience == policy.api_audience,
    ]
    if require_active:
        predicates.append(OAuthMcpService.is_active.is_(True))
    result = await session.execute(
        update(OAuthMcpService)
        .where(*predicates)
        .values(
            is_active=OAuthMcpService.is_active,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


async def load_service(
    session: AsyncSession, service_id: str | None, policy: OAuthPolicy
) -> ClientSnapshot | None:
    """只加载显式启用且同时匹配源/目标 audience 的服务，不授予任何业务 Scope。"""
    if not service_id:
        return None
    service = await session.get(OAuthMcpService, service_id, populate_existing=True)
    if (
        service is None
        or not service.is_active
        or not service.secret_hash
        or service.resource != policy.mcp_resource
        or service.api_audience != policy.api_audience
    ):
        return None
    return ClientSnapshot(
        client_id=service.service_id,
        redirect_uris=(),
        scopes=frozenset(),
        resource=service.resource,
        auth_method="client_secret_basic",
        secret_hash=service.secret_hash,
        kind="service",
        api_audience=service.api_audience,
    )


async def load_token_snapshot(
    session: AsyncSession,
    *,
    digest: str,
    policy: OAuthPolicy,
    now: datetime,
    allowed_kinds: tuple[str, ...] = ("access",),
    require_live: bool = True,
) -> TokenSnapshot | None:
    """严格按来源筛选凭证；自省和交换不接受 PAT、refresh 或 delegated 作为 access。"""
    token = await session.scalar(
        select(OAuthToken)
        .where(
            OAuthToken.token_hash == digest,
            OAuthToken.kind.in_(allowed_kinds),
        )
        .execution_options(populate_existing=True)
    )
    if token is None:
        return None
    grant = await session.get(OAuthGrant, token.grant_id, populate_existing=True)
    if (
        grant is None
        or grant.issuer != policy.issuer
        or grant.resource != policy.mcp_resource
    ):
        return None
    active = (
        token.revoked_at is None
        and token.consumed_at is None
        and token.expires_at > now
    )
    active = active and token.audience == policy.mcp_resource and bool(token.scopes)
    active = active and set(token.scopes) <= set(grant.scopes)
    if active:
        active = await load_live_grant(session, grant.grant_id, policy) is not None
    if active and token.family_id:
        family = await session.get(
            OAuthRefreshFamily, token.family_id, populate_existing=True
        )
        active = bool(
            family
            and family.grant_id == grant.grant_id
            and family.revoked_at is None
            and family.expires_at > now
            and token.expires_at <= family.expires_at
        )
    if require_live and not active:
        return None
    return TokenSnapshot(
        token.token_id,
        token.token_hash,
        grant.grant_id,
        grant.client_id,
        grant.user_id,
        grant.issuer,
        token.audience,
        frozenset(token.scopes),
        frozenset(grant.workspace_ids),
        token.kind,
        token.created_at,
        token.expires_at,
        now,
        active,
    )
