"""文件功能：收口 OAuth 授权围栏、单次凭证消费、轮换发行与无原始凭证的审计写入。"""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthAuthorizationCode, OAuthToken
from app.models.oauth_grant import OAuthGrant, OAuthRefreshFamily
from app.services.oauth.policy import OAuthPolicy
from app.services.oauth.protocol import RedactedToken, credential_digest
from app.services.oauth.snapshots import CredentialSnapshot


async def lock_grant(session: AsyncSession, grant_id: str, policy: OAuthPolicy) -> bool:
    """发行和撤销都首先 UPDATE 同一 Grant 行，在双方言上获得真实的事务互斥。"""
    result = await session.execute(
        update(OAuthGrant)
        .where(
            OAuthGrant.grant_id == grant_id,
            OAuthGrant.issuer == policy.issuer,
            OAuthGrant.resource == policy.mcp_resource,
            OAuthGrant.revoked_at.is_(None),
        )
        .values(version=OAuthGrant.version + 1)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def add_audit(
    session: AsyncSession,
    *,
    event: str,
    grant: OAuthGrant,
    now: datetime,
    token_id: str | None = None,
    service_id: str | None = None,
) -> OAuthAuditEvent:
    """仅记录内部固定事件名和公共身份，不接受任意 HTTP payload。"""
    audit = OAuthAuditEvent(
        event_id=uuid4().hex,
        event=event,
        user_id=grant.user_id,
        client_id=grant.client_id,
        grant_id=grant.grant_id,
        token_id=token_id,
        service_id=service_id,
        created_at=now,
    )
    session.add(audit)
    return audit


async def revoke_locked_grant(
    session: AsyncSession,
    grant: OAuthGrant,
    *,
    now: datetime,
    reason: str,
) -> OAuthAuditEvent:
    """在 Grant 锁内撤销授权/刷新家族并返回待提交审计；领域 Job 不受影响。"""
    grant.revoked_at = now
    grant.revocation_reason = reason
    await session.execute(
        update(OAuthRefreshFamily)
        .where(
            OAuthRefreshFamily.grant_id == grant.grant_id,
            OAuthRefreshFamily.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    return add_audit(session, event=reason, grant=grant, now=now)


async def persist_issuance(
    session: AsyncSession,
    *,
    credential: CredentialSnapshot,
    token: RedactedToken,
    policy: OAuthPolicy,
    now: datetime,
) -> bool:
    """在同一事务 CAS 消费来源并插入 access/refresh；返回 False 时调用方必须回滚。"""
    if credential.family_id is None:
        source = OAuthAuthorizationCode
        predicates = (source.code_hash == credential.credential_hash,)
        parent_id = None
        family = OAuthRefreshFamily(
            family_id=uuid4().hex,
            grant_id=credential.grant_id,
            created_at=now,
            expires_at=now + timedelta(seconds=policy.refresh_lifetime_seconds),
        )
    else:
        source = OAuthToken
        predicates = (
            source.token_hash == credential.credential_hash,
            source.kind == "refresh",
            source.revoked_at.is_(None),
        )
        parent_id = await session.scalar(select(source.token_id).where(*predicates))
        family = await session.get(OAuthRefreshFamily, credential.family_id)
        if family is None or family.revoked_at is not None or family.expires_at <= now:
            return False
    consumed = await session.execute(
        update(source)
        .where(
            *predicates,
            source.grant_id == credential.grant_id,
            source.consumed_at.is_(None),
            source.expires_at > now,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        return False
    if credential.family_id is None:
        session.add(family)
        await session.flush()
    access_expiry = min(
        now + timedelta(seconds=policy.access_ttl_seconds), family.expires_at
    )
    token["expires_in"] = max(0, int((access_expiry - now).total_seconds()))
    scopes = sorted(set(token["scope"].split()))
    for key, kind, expiry in (
        ("access_token", "access", access_expiry),
        ("refresh_token", "refresh", family.expires_at),
    ):
        session.add(
            OAuthToken(
                token_id=uuid4().hex,
                token_hash=credential_digest(token[key]),
                grant_id=credential.grant_id,
                kind=kind,
                audience=policy.mcp_resource,
                scopes=scopes,
                family_id=family.family_id,
                parent_token_id=parent_id,
                created_at=now,
                expires_at=expiry,
            )
        )
    return True
