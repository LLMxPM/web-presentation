"""文件功能：使用独立 SQLite/PG 数据库验证 FastAPI→Authlib→原子消费、轮换及撤销。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import app.models  # noqa: F401
import pytest
from app.core.time_utils import utc_now
from app.models.oauth_audit import OAuthAuditEvent
from app.models.oauth_credential import OAuthAuthorizationCode, OAuthToken
from app.models.oauth_grant import OAuthGrant, OAuthRefreshFamily
from app.models.oauth_registration import OAuthClient
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.services.oauth.grant_service import OAuthGrantService
from app.services.oauth.protocol import credential_digest
from app.services.oauth.request import ProtocolRequest
from app.services.oauth.token_service import OAuthTokenService
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from tests.fixtures.oauth import POLICY, REDIRECT, SCOPES, request_data, token_request


def probe_app(factory) -> FastAPI:
    """仅测试中装配最小 FastAPI 适配入口，生产 app 尚未公开 OAuth 端点。"""
    app = FastAPI()
    service = OAuthTokenService(factory, POLICY)

    @app.post("/oauth/token")
    async def token_endpoint(request: Request):
        """异步读取重复参数，等待数据库提交后才转换为 HTTP Response。"""
        form = await request.form()
        protocol = ProtocolRequest(
            method=request.method,
            uri=POLICY.issuer + "/oauth/token",
            pairs=form.multi_items(),
            headers=request.headers,
        )
        result = await service.token_response(protocol)
        return JSONResponse(
            result.body, status_code=result.status_code, headers=dict(result.headers)
        )

    return app


async def test_fastapi_invalid_pkce_and_single_code_consumption(oauth_database) -> None:
    """无效 PKCE 不消费；两个独立服务实例并发兑换只有一次成功和一组持久化 Token。"""
    transports = [ASGITransport(app=probe_app(oauth_database)) for _ in range(2)]
    async with AsyncClient(transport=transports[0], base_url=POLICY.issuer) as first:
        invalid = await first.post(
            "/oauth/token", data=request_data(code_verifier="b" * 48)
        )
        assert invalid.json()["error"] == "invalid_grant"
        async with oauth_database() as session:
            code = await session.get(
                OAuthAuthorizationCode, credential_digest("original-code")
            )
            assert code.consumed_at is None
        async with AsyncClient(
            transport=transports[1], base_url=POLICY.issuer
        ) as second:
            results = await asyncio.gather(
                first.post("/oauth/token", data=request_data()),
                second.post("/oauth/token", data=request_data()),
            )
    assert sorted(response.status_code for response in results) == [200, 400]
    success = next(response for response in results if response.status_code == 200)
    failure = next(response for response in results if response.status_code == 400)
    assert failure.json()["error"] == "invalid_grant"
    assert "access_token" not in failure.json()
    async with oauth_database() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(OAuthRefreshFamily))
            == 1
        )
        hashes = set(await session.scalars(select(OAuthToken.token_hash)))
        assert hashes == {
            credential_digest(success.json()[key])
            for key in ("access_token", "refresh_token")
        }
        assert (
            await session.scalar(select(func.count()).select_from(OAuthAuditEvent)) == 1
        )


async def test_concurrent_refresh_replay_revokes_whole_chain(oauth_database) -> None:
    """独立会话只允许一次轮换；竞争失败被认作重放并使整个授权链立即失效。"""
    service = OAuthTokenService(oauth_database, POLICY)
    issued = await service.token_response(token_request(request_data()))
    data = {
        "grant_type": "refresh_token",
        "client_id": "desktop",
        "resource": POLICY.mcp_resource,
        "refresh_token": issued.body["refresh_token"],
        "scope": "page:read",
    }
    results = await asyncio.gather(
        *(
            OAuthTokenService(oauth_database, POLICY).token_response(
                token_request(data)
            )
            for _ in range(2)
        )
    )
    assert sorted(response.status_code for response in results) == [200, 400]
    success = next(response for response in results if response.status_code == 200)
    assert success.body["scope"] == "page:read"
    async with oauth_database() as session:
        grant = await session.get(OAuthGrant, "grant-1")
        assert (
            grant.revoked_at is not None and grant.revocation_reason == "refresh_replay"
        )
        family = await session.scalar(select(OAuthRefreshFamily))
        assert family.revoked_at is not None
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 4
        events = set(await session.scalars(select(OAuthAuditEvent.event)))
        assert events == {"code_consumed", "refresh_rotated", "refresh_replay"}
    data["refresh_token"] = success.body["refresh_token"]
    assert (await service.token_response(token_request(data))).body[
        "error"
    ] == "invalid_grant"


async def test_refresh_absolute_expiry_and_reduced_scope(oauth_database) -> None:
    """刷新不能延长家族期限；下一代 access 与 refresh 均保持缩小后的 Scope。"""
    service = OAuthTokenService(oauth_database, POLICY)
    issued = await service.token_response(token_request(request_data()))
    shortened = utc_now() + timedelta(seconds=20)
    async with oauth_database() as session:
        await session.execute(update(OAuthRefreshFamily).values(expires_at=shortened))
        await session.commit()
    data = {
        "grant_type": "refresh_token",
        "client_id": "desktop",
        "resource": POLICY.mcp_resource,
        "refresh_token": issued.body["refresh_token"],
        "scope": "page:read",
    }
    rotated = await service.token_response(token_request(data))
    assert rotated.status_code == 200 and 0 < rotated.body["expires_in"] <= 20
    async with oauth_database() as session:
        tokens = list(
            await session.scalars(
                select(OAuthToken).where(
                    OAuthToken.token_hash.in_(
                        [
                            credential_digest(rotated.body[key])
                            for key in ("access_token", "refresh_token")
                        ]
                    )
                )
            )
        )
        assert all(
            token.scopes == ["page:read"] and token.expires_at <= shortened
            for token in tokens
        )
        assert all(token.parent_token_id for token in tokens)


async def test_user_revoke_is_owner_scoped_idempotent_and_fences_issuance(
    oauth_database,
) -> None:
    """他人不能撤销 Grant；本人撤销与发行共用锁，撤销后不存在迟到有效凭证。"""
    grants = OAuthGrantService(oauth_database, POLICY)
    assert await grants.revoke(user_id=2, grant_id="grant-1") is False
    results = await asyncio.gather(
        grants.revoke(user_id=1, grant_id="grant-1"),
        OAuthTokenService(oauth_database, POLICY).token_response(
            token_request(request_data())
        ),
    )
    assert results[0] is True
    assert results[1].status_code in {200, 400}
    assert await grants.revoke(user_id=1, grant_id="grant-1") is True
    assert await grants.revoke(user_id=1, grant_id="unknown") is False
    response = await OAuthTokenService(oauth_database, POLICY).token_response(
        token_request(request_data())
    )
    assert response.body["error"] == "invalid_grant"
    async with oauth_database() as session:
        grant = await session.get(OAuthGrant, "grant-1")
        assert grant.revoked_at is not None


@pytest.mark.parametrize(
    "target", ["user", "client", "membership", "scope", "issuer", "resource"]
)
async def test_live_authority_changes_prevent_issuance(oauth_database, target) -> None:
    """平台主体或授权边界变动在每次请求实时检查，不等访问凭证自然过期。"""
    async with oauth_database() as session:
        changes = {
            "user": update(User).values(status="disabled"),
            "client": update(OAuthClient).values(is_active=False),
            "membership": update(WorkspaceMember).values(status="disabled"),
            "scope": update(OAuthGrant).values(scopes=["page:read"]),
            "issuer": update(OAuthGrant).values(issuer="https://wrong.example.test"),
            "resource": update(OAuthGrant).values(
                resource="https://wrong.example.test/mcp"
            ),
        }
        await session.execute(changes[target])
        await session.commit()
    result = await OAuthTokenService(oauth_database, POLICY).token_response(
        token_request(request_data())
    )
    assert result.status_code in {400, 401} and "access_token" not in result.body
    async with oauth_database() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 0


async def test_commit_failure_never_delivers_token_or_consumes_code(
    oauth_database, monkeypatch
) -> None:
    """提交故障向调用方抛出错误，暂存成功不得交付，Session 关闭回滚所有修改。"""
    from sqlalchemy.ext.asyncio import AsyncSession

    async def fail_commit(self) -> None:
        """在实际数据库事务提交前注入故障。"""
        raise RuntimeError("commit unavailable")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit unavailable"):
        await OAuthTokenService(oauth_database, POLICY).token_response(
            token_request(request_data())
        )
    async with oauth_database() as session:
        assert await session.scalar(select(func.count()).select_from(OAuthToken)) == 0
        code = await session.get(
            OAuthAuthorizationCode, credential_digest("original-code")
        )
        assert code.consumed_at is None


async def test_other_registered_client_cannot_trigger_refresh_replay_revocation(
    oauth_database,
) -> None:
    """别的真实客户端使用泄漏旧 Token 也不能借重放规则撤销原用户授权。"""
    service = OAuthTokenService(oauth_database, POLICY)
    issued = await service.token_response(token_request(request_data()))
    data = {
        "grant_type": "refresh_token",
        "client_id": "desktop",
        "resource": POLICY.mcp_resource,
        "refresh_token": issued.body["refresh_token"],
    }
    assert (await service.token_response(token_request(data))).status_code == 200
    async with oauth_database() as session:
        session.add(
            OAuthClient(
                client_id="other",
                name="别的客户端",
                redirect_uris=[REDIRECT],
                scopes=SCOPES,
                resource=POLICY.mcp_resource,
                auth_method="none",
            )
        )
        await session.commit()
    data["client_id"] = "other"
    assert (await service.token_response(token_request(data))).body[
        "error"
    ] == "invalid_grant"
    async with oauth_database() as session:
        assert (await session.get(OAuthGrant, "grant-1")).revoked_at is None
