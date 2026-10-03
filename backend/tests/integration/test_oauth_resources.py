"""文件功能：验证受信服务自省、整链撤销、受控交换及 API 委托来源链的正反例。"""

import pytest
from app.models.oauth_credential import OAuthToken
from app.models.oauth_grant import OAuthGrant
from app.models.oauth_registration import OAuthClient
from app.services.oauth.delegated_identity import authenticate_delegated
from app.services.oauth.protocol import credential_digest
from app.services.oauth.resource_protocol import ACCESS_TOKEN_TYPE
from app.services.oauth.resource_service import OAuthResourceService
from sqlalchemy import select

from tests.fixtures.oauth import POLICY, REDIRECT, SCOPES, token_request
from tests.fixtures.oauth_resource import exchange_data, service_request


async def test_live_introspection_exchange_and_principal(
    oauth_database, mcp_access
) -> None:
    """自省 DTO 描述原用户授权；交换结果归一到业务主体并且没有刷新能力。"""
    service = OAuthResourceService(oauth_database, POLICY)
    introspected = await service.response(
        "introspection", service_request({"token": mcp_access["access_token"]})
    )
    assert introspected.status_code == 200
    assert introspected.body["active"] is True and introspected.body["wp_version"] == 1
    assert introspected.body["aud"] == POLICY.mcp_resource
    assert introspected.body["iss"] == POLICY.issuer and introspected.body["sub"] == "1"
    assert introspected.body["client_id"] == "desktop" and introspected.body[
        "workspace_ids"
    ] == [1]
    assert "no-store" in dict(introspected.headers)["Cache-Control"]
    exchanged = await service.response(
        "exchange", service_request(exchange_data(mcp_access["access_token"]))
    )
    assert exchanged.status_code == 200
    assert exchanged.body["issued_token_type"] == ACCESS_TOKEN_TYPE
    assert exchanged.body["access_token"].startswith("wp_dlg_")
    assert (
        0 < exchanged.body["expires_in"] <= 60 and "refresh_token" not in exchanged.body
    )
    async with oauth_database() as session:
        principal = await authenticate_delegated(
            session, exchanged.body["access_token"], POLICY
        )
        assert principal.user.id == 1 and principal.scopes == frozenset({"page:read"})
        assert (
            principal.workspace_ids == frozenset({1})
            and principal.all_workspaces is False
        )
        assert principal.credential.service_id == "mcp-service"
        assert (
            principal.credential.client_id == "desktop"
            and principal.credential.audience == POLICY.api_audience
        )
        token = await session.scalar(
            select(OAuthToken).where(OAuthToken.kind == "delegated")
        )
        source = await session.get(OAuthToken, token.source_token_id)
        assert token.expires_at <= source.expires_at
        assert token.token_hash == credential_digest(exchanged.body["access_token"])


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"resource": "https://other.test/api/v1"}, "invalid_request"),
        ({"scope": "page:write asset:read"}, "invalid_scope"),
        ({"actor_token": "another-actor"}, "invalid_request"),
        ({"audience": "https://other.test"}, "invalid_request"),
        (
            {"subject_token_type": "urn:ietf:params:oauth:token-type:jwt"},
            "invalid_request",
        ),
        (
            {"requested_token_type": "urn:ietf:params:oauth:token-type:refresh_token"},
            "invalid_request",
        ),
    ],
)
async def test_exchange_rejects_expansion_or_impersonation(
    oauth_database, mcp_access, changes, error
) -> None:
    """不支持的交换参数不能换取更多权限、其他服务身份或用户刷新凭证。"""
    response = await OAuthResourceService(oauth_database, POLICY).response(
        "exchange",
        service_request(exchange_data(mcp_access["access_token"], **changes)),
    )
    assert response.body["error"] == error
    assert "access_token" not in response.body


@pytest.mark.parametrize("source", ["pat", "refresh", "delegated", "unknown"])
async def test_access_source_cannot_be_substituted(
    oauth_database, mcp_access, source
) -> None:
    """PAT/refresh/delegated 均不能作为 MCP access 再交换或被服务自省放行。"""
    service = OAuthResourceService(oauth_database, POLICY)
    if source == "delegated":
        issued = await service.response(
            "exchange", service_request(exchange_data(mcp_access["access_token"]))
        )
        raw = issued.body["access_token"]
    elif source == "refresh":
        raw = mcp_access["refresh_token"]
    else:
        raw = "wp_pat_fake" if source == "pat" else "unrecognized"
    response = await service.response("exchange", service_request(exchange_data(raw)))
    assert response.body["error"] == "invalid_grant"
    introspected = await service.response(
        "introspection", service_request({"token": raw})
    )
    assert introspected.body == {"active": False}


async def test_service_authentication_and_duplicate_parameters(
    oauth_database, mcp_access
) -> None:
    """错误密钥、非服务客户端、缺失认证及重复 resource 均在发行前失败。"""
    service = OAuthResourceService(oauth_database, POLICY)
    data = exchange_data(mcp_access["access_token"])
    for request in (
        service_request(data, secret="wrong"),
        service_request(data, service_id="desktop"),
        token_request(data),
        service_request(data, extra=[("resource", POLICY.api_audience)]),
    ):
        response = await service.response("exchange", request)
        assert (
            response.status_code in {400, 401} and "access_token" not in response.body
        )


async def test_client_revocation_is_idempotent_and_hides_foreign_tokens(
    oauth_database, mcp_access
) -> None:
    """所属客户端撤销整链；其他客户端或未知 Token 都不暴露存在性、不改原授权。"""
    service = OAuthResourceService(oauth_database, POLICY)
    async with oauth_database() as session:
        session.add(
            OAuthClient(
                client_id="other",
                name="其他客户端",
                redirect_uris=[REDIRECT],
                scopes=SCOPES,
                resource=POLICY.mcp_resource,
                auth_method="none",
            )
        )
        await session.commit()
    foreign = await service.response(
        "revocation",
        token_request(
            {
                "client_id": "other",
                "token": mcp_access["access_token"],
            }
        ),
    )
    assert foreign.status_code == 200 and foreign.body == {}
    async with oauth_database() as session:
        assert (await session.get(OAuthGrant, "grant-1")).revoked_at is None
    for raw in ("unknown", mcp_access["access_token"]):
        response = await service.response(
            "revocation", token_request({"client_id": "desktop", "token": raw})
        )
        assert response.status_code == 200 and response.body == {}
    repeat = await service.response(
        "revocation",
        token_request({"client_id": "desktop", "token": mcp_access["refresh_token"]}),
    )
    assert repeat.status_code == 200 and repeat.body == {}
    assert (
        await service.response(
            "introspection", service_request({"token": mcp_access["access_token"]})
        )
    ).body == {"active": False}
    assert (
        await service.response(
            "exchange", service_request(exchange_data(mcp_access["access_token"]))
        )
    ).body["error"] == "invalid_grant"
