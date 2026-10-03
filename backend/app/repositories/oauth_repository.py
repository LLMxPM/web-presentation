"""文件功能：查询 OAuth 注册及授权实时状态，转换为无 ORM 依赖的 Authlib 快照。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecordStatus
from app.models.oauth_credential import OAuthAuthorizationCode, OAuthToken
from app.models.oauth_grant import OAuthGrant, OAuthRefreshFamily
from app.models.oauth_registration import OAuthClient
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.snapshots import ClientSnapshot, CredentialSnapshot


async def load_client(
    session: AsyncSession, client_id: str | None, policy: OAuthPolicy
) -> ClientSnapshot | None:
    """拒绝停用、错误资源或不完整密钥配置的客户端；客户端名不是认证证据。"""
    if not client_id:
        return None
    client = await session.get(OAuthClient, client_id, populate_existing=True)
    if client is None or not client.is_active or client.resource != policy.mcp_resource:
        return None
    if client.auth_method == "none" and client.secret_hash is not None:
        return None
    if client.auth_method == "client_secret_basic" and not client.secret_hash:
        return None
    return ClientSnapshot(
        client.client_id,
        tuple(client.redirect_uris),
        frozenset(client.scopes),
        client.resource,
        client.auth_method,
        client.secret_hash,
    )


async def load_live_grant(
    session: AsyncSession, grant_id: str, policy: OAuthPolicy
) -> OAuthGrant | None:
    """每次发行/自省检查用户、客户端、范围和全部实时空间成员资格，无放行缓存。"""
    grant = await session.get(OAuthGrant, grant_id, populate_existing=True)
    if (
        grant is None
        or grant.revoked_at is not None
        or grant.issuer != policy.issuer
        or grant.resource != policy.mcp_resource
    ):
        return None
    client = await load_client(session, grant.client_id, policy)
    user = await session.get(User, grant.user_id, populate_existing=True)
    if client is None or user is None or user.status != RecordStatus.ACTIVE.value:
        return None
    if (
        not grant.scopes
        or not frozenset(grant.scopes) <= client.scopes
        or not grant.workspace_ids
    ):
        return None
    if any(
        type(workspace_id) is not int or workspace_id <= 0
        for workspace_id in grant.workspace_ids
    ):
        return None
    members = set(
        await session.scalars(
            select(WorkspaceMember.workspace_id)
            .join(
                Workspace,
                Workspace.id == WorkspaceMember.workspace_id,
            )
            .where(
                WorkspaceMember.user_id == grant.user_id,
                WorkspaceMember.status == RecordStatus.ACTIVE.value,
                WorkspaceMember.workspace_id.in_(grant.workspace_ids),
                Workspace.status == RecordStatus.ACTIVE.value,
                Workspace.deleted_at.is_(None),
            )
        )
    )
    if members != set(grant.workspace_ids):
        return None
    return grant


async def load_credential(
    session: AsyncSession,
    *,
    kind: str,
    digest: str,
    client_id: str | None,
    policy: OAuthPolicy,
    now: datetime,
) -> CredentialSnapshot | None:
    """预读授权码/刷新快照；保留刷新消费状态供已认证客户端识别重放。"""
    if kind == "authorization_code":
        source = await session.get(
            OAuthAuthorizationCode, digest, populate_existing=True
        )
    elif kind == "refresh_token":
        source = await session.scalar(
            select(OAuthToken)
            .where(
                OAuthToken.token_hash == digest,
                OAuthToken.kind == "refresh",
            )
            .execution_options(populate_existing=True)
        )
    else:
        return None
    if source is None or source.expires_at <= now:
        return None
    grant = await load_live_grant(session, source.grant_id, policy)
    if (
        grant is None
        or grant.client_id != client_id
        or not set(source.scopes) <= set(grant.scopes)
    ):
        return None
    family_id = None
    if isinstance(source, OAuthToken):
        family = await session.get(
            OAuthRefreshFamily, source.family_id, populate_existing=True
        )
        if (
            source.revoked_at is not None
            or source.audience != policy.mcp_resource
            or family is None
            or family.grant_id != grant.grant_id
            or family.revoked_at is not None
            or family.expires_at <= now
        ):
            return None
        family_id = family.family_id
    return CredentialSnapshot(
        credential_hash=digest,
        grant_id=grant.grant_id,
        client_id=grant.client_id,
        user_id=grant.user_id,
        resource=grant.resource,
        scopes=frozenset(source.scopes),
        expires_at=source.expires_at,
        consumed=source.consumed_at is not None,
        redirect_uri=source.redirect_uri
        if isinstance(source, OAuthAuthorizationCode)
        else None,
        code_challenge=source.code_challenge
        if isinstance(source, OAuthAuthorizationCode)
        else None,
        code_challenge_method=source.code_challenge_method
        if isinstance(source, OAuthAuthorizationCode)
        else None,
        family_id=family_id,
    )
