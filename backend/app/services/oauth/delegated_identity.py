"""文件功能：验证不透明 API 委托凭证及完整来源链，验证完成后构造统一外部主体。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.enums import RecordStatus
from app.models.oauth_credential import OAuthToken
from app.models.user import User
from app.repositories.oauth_repository import load_live_grant
from app.repositories.oauth_resource_repository import load_service, load_token_snapshot
from app.services.external_principal import DelegatedCredential, ExternalPrincipal
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.protocol import credential_digest


async def authenticate_delegated(
    session: AsyncSession,
    raw: str,
    policy: OAuthPolicy,
) -> ExternalPrincipal:
    """逐请求验证 issuer/audience/期限/Grant/用户/成员/服务/源 access，不允许认证回退。"""
    invalid = AppException(
        status_code=401, code="UNAUTHENTICATED", detail="委托访问凭证无效或已失效。"
    )
    if not raw.startswith("wp_dlg_"):
        raise invalid
    now = utc_now()
    token = await session.scalar(
        select(OAuthToken)
        .where(
            OAuthToken.token_hash == credential_digest(raw),
            OAuthToken.kind == "delegated",
        )
        .execution_options(populate_existing=True)
    )
    if (
        token is None
        or token.revoked_at is not None
        or token.consumed_at is not None
        or token.expires_at <= now
        or token.audience != policy.api_audience
        or not token.source_token_id
        or not token.service_id
    ):
        raise invalid
    grant = await load_live_grant(session, token.grant_id, policy)
    service = await load_service(session, token.service_id, policy)
    source = await session.get(
        OAuthToken, token.source_token_id, populate_existing=True
    )
    if grant is None or service is None or source is None or source.kind != "access":
        raise invalid
    live_source = await load_token_snapshot(
        session, digest=source.token_hash, policy=policy, now=now
    )
    if (
        live_source is None
        or live_source.grant_id != token.grant_id
        or token.expires_at > live_source.expires_at
        or token.expires_at <= token.created_at
        or (token.expires_at - token.created_at).total_seconds()
        > policy.delegated_ttl_seconds
        or not token.scopes
        or not frozenset(token.scopes) <= live_source.scopes
    ):
        raise invalid
    user = await session.get(User, grant.user_id, populate_existing=True)
    if user is None or user.status != RecordStatus.ACTIVE.value:
        raise invalid
    return ExternalPrincipal(
        user=user,
        workspace_ids=frozenset(grant.workspace_ids),
        scopes=frozenset(token.scopes),
        credential=DelegatedCredential(
            public_id=token.token_id,
            grant_id=grant.grant_id,
            client_id=grant.client_id,
            service_id=token.service_id,
            issuer=grant.issuer,
            audience=token.audience,
            expires_at=token.expires_at,
        ),
    )
