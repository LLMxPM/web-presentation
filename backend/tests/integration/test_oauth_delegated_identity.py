"""文件功能：验证 API 委托凭证的期限、实时授权、来源链与提交故障边界。"""

from datetime import timedelta

import pytest
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.oauth_credential import OAuthToken
from app.models.oauth_grant import OAuthGrant
from app.models.oauth_registration import OAuthMcpService
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.services.oauth.delegated_identity import authenticate_delegated
from app.services.oauth.grant_service import OAuthGrantService
from app.services.oauth.resource_service import OAuthResourceService
from sqlalchemy import select, update

from tests.fixtures.oauth import POLICY, SCOPES
from tests.fixtures.oauth_resource import exchange_data, service_request


@pytest.mark.parametrize(
    "target",
    ["grant", "user", "membership", "service", "source", "audience", "scope", "expiry"],
)
async def test_delegated_checks_full_live_chain(
    oauth_database, mcp_access, target
) -> None:
    """委托凭证每请求复核整个来源链，期限内的 Token 也不能绕过实时授权变化。"""
    service = OAuthResourceService(oauth_database, POLICY)
    issued = await service.response(
        "exchange", service_request(exchange_data(mcp_access["access_token"]))
    )
    raw = issued.body["access_token"]
    async with oauth_database() as session:
        changes = {
            "grant": update(OAuthGrant).values(revoked_at=utc_now()),
            "user": update(User).values(status="disabled"),
            "membership": update(WorkspaceMember).values(status="disabled"),
            "service": update(OAuthMcpService).values(is_active=False),
            "source": update(OAuthToken)
            .where(OAuthToken.kind == "access")
            .values(revoked_at=utc_now()),
            "audience": update(OAuthToken)
            .where(OAuthToken.kind == "delegated")
            .values(audience=POLICY.mcp_resource),
            "scope": update(OAuthToken)
            .where(OAuthToken.kind == "delegated")
            .values(scopes=["asset:read"]),
            "expiry": update(OAuthToken)
            .where(OAuthToken.kind == "delegated")
            .values(expires_at=utc_now() - timedelta(seconds=1)),
        }
        await session.execute(changes[target])
        await session.commit()
        with pytest.raises(AppException) as denied:
            await authenticate_delegated(session, raw, POLICY)
        assert denied.value.status_code == 401


async def test_delegated_expiry_bound_to_source_and_owner_revocation(
    oauth_database, mcp_access
) -> None:
    """源 access 只余 10 秒时，委托不能以自身默认 60 秒延长授权。"""
    async with oauth_database() as session:
        await session.execute(
            update(OAuthToken)
            .where(OAuthToken.kind == "access")
            .values(expires_at=utc_now() + timedelta(seconds=10))
        )
        await session.commit()
    service = OAuthResourceService(oauth_database, POLICY)
    issued = await service.response(
        "exchange", service_request(exchange_data(mcp_access["access_token"]))
    )
    assert issued.status_code == 200 and 0 < issued.body["expires_in"] <= 10
    assert await OAuthGrantService(oauth_database, POLICY).revoke(
        user_id=1, grant_id="grant-1"
    )
    async with oauth_database() as session:
        with pytest.raises(AppException):
            await authenticate_delegated(session, issued.body["access_token"], POLICY)


async def test_exchange_commit_failure_keeps_no_delegated_token(
    oauth_database, mcp_access, monkeypatch
) -> None:
    """提交失败不能交付协议核暂存的 delegated，也不能落库或写成功审计。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    async def fail_commit(self) -> None:
        """在实际 commit 前注入故障。"""
        raise RuntimeError("exchange commit unavailable")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="exchange commit unavailable"):
        await OAuthResourceService(oauth_database, POLICY).response(
            "exchange", service_request(exchange_data(mcp_access["access_token"]))
        )
    async with oauth_database() as session:
        assert (
            await session.scalar(
                select(OAuthToken.token_id).where(OAuthToken.kind == "delegated")
            )
            is None
        )


async def test_delegated_rejects_cross_grant_source(oauth_database, mcp_access) -> None:
    """即使另一来源也有效且属于同一用户，委托也必须绑定原 Grant。"""
    issued = await OAuthResourceService(oauth_database, POLICY).response(
        "exchange", service_request(exchange_data(mcp_access["access_token"]))
    )
    async with oauth_database() as session:
        session.add(
            OAuthGrant(
                grant_id="other-grant",
                user_id=1,
                client_id="desktop",
                issuer=POLICY.issuer,
                resource=POLICY.mcp_resource,
                workspace_ids=[1],
                scopes=SCOPES,
            )
        )
        await session.flush()
        await session.execute(
            update(OAuthToken)
            .where(OAuthToken.kind == "access")
            .values(grant_id="other-grant", family_id=None)
        )
        await session.commit()
        with pytest.raises(AppException):
            await authenticate_delegated(session, issued.body["access_token"], POLICY)
