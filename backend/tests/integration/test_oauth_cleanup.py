"""文件功能：验证 OAuth 清理的重放证据、来源图外键、有界预检及失败回滚。"""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from app.core.time_utils import utc_now
from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthAuthorizationCode, OAuthToken
from app.models.oauth_grant import OAuthConsentRequest, OAuthGrant, OAuthRefreshFamily
from app.models.oauth_registration import OAuthClient, OAuthMcpService
from app.models.user import UserSession
from app.services.oauth.cleanup_service import OAuthCleanupService
from app.services.oauth.protocol import credential_digest
from app.services.oauth.resource_service import OAuthResourceService
from app.services.oauth.token_service import OAuthTokenService
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.oauth import POLICY, REDIRECT, token_request
from tests.fixtures.oauth_resource import exchange_data, service_request


def refresh_request(raw):
    """构造原客户端刷新，用于验证清理后已消费凭证仍能识别重放。"""
    return token_request(
        {
            "grant_type": "refresh_token",
            "client_id": "desktop",
            "resource": POLICY.mcp_resource,
            "refresh_token": raw,
        }
    )


async def test_consumed_refresh_survives_cleanup_and_still_detects_replay(
    oauth_database, mcp_access
):
    """消费超过七天而家族仍活跃时必须保留原摘要；清理后重放仍撤销整链。"""
    service = OAuthTokenService(oauth_database, POLICY)
    old_raw = mcp_access["refresh_token"]
    assert (await service.token_response(refresh_request(old_raw))).status_code == 200
    async with oauth_database() as session:
        await session.execute(
            update(OAuthToken)
            .where(OAuthToken.token_hash == credential_digest(old_raw))
            .values(
                consumed_at=utc_now() - timedelta(days=8),
                created_at=utc_now() - timedelta(days=9),
            )
        )
        await session.commit()
    assert (await OAuthCleanupService(oauth_database).sweep())["refresh"] == 0
    result = await service.token_response(refresh_request(old_raw))
    assert result.body["error"] == "invalid_grant"
    async with oauth_database() as session:
        grant = await session.get(OAuthGrant, "grant-1")
        assert grant.revocation_reason == "refresh_replay"


async def test_cleanup_reclaims_expired_graph_from_children_without_cascade(
    oauth_database, mcp_access
):
    """多代 refresh 和 delegated 来源先删后代，外键启用时仍可收敛且保留 Grant。"""
    rotated = await OAuthTokenService(oauth_database, POLICY).token_response(
        refresh_request(mcp_access["refresh_token"])
    )
    assert (
        await OAuthResourceService(oauth_database, POLICY).response(
            "exchange",
            service_request(exchange_data(rotated.body["access_token"])),
        )
    ).status_code == 200
    old = utc_now() - timedelta(days=8)
    async with oauth_database() as session:
        for model in (OAuthToken, OAuthAuthorizationCode, OAuthRefreshFamily):
            await session.execute(update(model).values(expires_at=old))
        await session.commit()
    cleaner = OAuthCleanupService(oauth_database)
    preview = await cleaner.sweep(dry_run=True)
    assert preview["delegated"] == 1 and preview["codes"] == 1
    async with oauth_database() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 5
    totals = [await cleaner.sweep() for _ in range(3)]
    assert sum(row["delegated"] for row in totals) == 1
    assert sum(row["access"] for row in totals) == 2
    assert sum(row["refresh"] for row in totals) == 2
    assert sum(row["families"] for row in totals) == 1
    async with oauth_database() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 0
        assert await session.get(OAuthGrant, "grant-1") is not None
        assert await session.get(OAuthClient, "desktop") is not None
        assert await session.get(OAuthMcpService, "mcp-service") is not None
    assert not any((await cleaner.sweep()).values())


async def test_cleanup_preserves_source_referenced_by_retained_delegation(
    oauth_database, mcp_access
):
    """源 access 已超过保留期但后代尚在保留期时，来源链不能被删除或级联。"""
    issued = await OAuthResourceService(oauth_database, POLICY).response(
        "exchange",
        service_request(exchange_data(mcp_access["access_token"])),
    )
    async with oauth_database() as session:
        delegated = await session.scalar(
            select(OAuthToken).where(OAuthToken.kind == "delegated")
        )
        source_id = delegated.source_token_id
        await session.execute(
            update(OAuthToken)
            .where(OAuthToken.token_id == source_id)
            .values(
                expires_at=utc_now() - timedelta(days=8),
            )
        )
        await session.commit()
    counts = await OAuthCleanupService(oauth_database).sweep()
    assert counts["access"] == 0 and counts["delegated"] == 0
    assert issued.status_code == 200
    async with oauth_database() as session:
        assert await session.get(OAuthToken, source_id) is not None


async def test_cleanup_revoked_grant_waits_retention_and_removes_future_refresh(
    oauth_database, mcp_access
):
    """Grant 最近撤销保留证据，超过七天后可删绝对到期时间仍在未来的刷新链。"""
    now = utc_now()
    async with oauth_database() as session:
        await session.execute(
            update(OAuthGrant).values(revoked_at=now, revocation_reason="user_revoked")
        )
        await session.execute(update(OAuthRefreshFamily).values(revoked_at=now))
        await session.commit()
    cleaner = OAuthCleanupService(oauth_database)
    assert not any((await cleaner.sweep(now=now)).values())
    counts = await cleaner.sweep(now=now + timedelta(days=8))
    assert counts["access"] == 1 and counts["refresh"] == 1 and counts["families"] == 1


async def test_cleanup_batch_limit_audit_retention_and_consent(oauth_database):
    """每类批次有界；30 天审计与七天到期确认分别清理，预检不会消费或删除。"""
    now = utc_now()
    async with oauth_database() as session:
        session.add(
            UserSession(
                id=1,
                user_id=1,
                token_hash="unused-cookie",
                expires_at=now + timedelta(days=1),
                last_active_at=now,
            )
        )
        await session.flush()
        for days in (31, 32, 33, 1):
            session.add(
                OAuthAuditEvent(
                    event_id=uuid4().hex,
                    event="authorized",
                    created_at=now - timedelta(days=days),
                )
            )
        for days in (8, 9, 1):
            session.add(
                OAuthConsentRequest(
                    request_id=uuid4().hex,
                    user_id=1,
                    session_id=1,
                    client_id="desktop",
                    redirect_uri=REDIRECT,
                    resource=POLICY.mcp_resource,
                    scopes=["page:read"],
                    state=None,
                    code_challenge="challenge",
                    code_challenge_method="S256",
                    csrf_hash="unused",
                    created_at=now - timedelta(days=10),
                    expires_at=now - timedelta(days=days),
                )
            )
        await session.commit()
    cleaner = OAuthCleanupService(oauth_database, batch_size=1)
    assert (await cleaner.sweep(dry_run=True, now=now))["audits"] == 1
    for _ in range(3):
        counts = await cleaner.sweep(now=now)
        assert max(counts.values()) <= 1
    async with oauth_database() as session:
        assert (
            await session.scalar(select(func.count()).select_from(OAuthAuditEvent)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(OAuthConsentRequest))
            == 1
        )


async def test_cleanup_commit_failure_rolls_back_all_deletes(
    oauth_database, monkeypatch
):
    """整个批次提交失败时不丢失任何记录，后续可以重试。"""
    async with oauth_database() as session:
        await session.execute(
            update(OAuthAuthorizationCode).values(
                expires_at=utc_now() - timedelta(days=8)
            )
        )
        await session.commit()

    async def fail_commit(self):
        """注入事务提交故障。"""
        raise RuntimeError("commit unavailable")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        await OAuthCleanupService(oauth_database).sweep()
    async with oauth_database() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(OAuthAuthorizationCode)
            )
            == 1
        )


async def test_concurrent_cleaners_have_no_double_delete(oauth_database, mcp_access):
    """两个独立服务同时清理只有一个实际删除各条记录，并保持来源外键。"""
    async with oauth_database() as session:
        await session.execute(
            update(OAuthAuthorizationCode).values(
                expires_at=utc_now() - timedelta(days=8)
            )
        )
        await session.commit()
    counts = await asyncio.gather(
        *[OAuthCleanupService(oauth_database).sweep() for _ in range(2)]
    )
    assert sum(row["codes"] for row in counts) == 1
