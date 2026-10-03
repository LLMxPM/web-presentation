"""文件功能：验证受信交换后的真实委托 Bearer 访问现有 External 路由及整链实时撤销边界。"""

from urllib.parse import parse_qs, urlsplit

import pytest
from app.models.oauth_credential import OAuthToken
from app.models.oauth_registration import OAuthMcpService
from app.models.workspace import Workspace, WorkspaceMember
from sqlalchemy import update

from tests.fixtures.oauth import POLICY, VERIFIER
from tests.fixtures.oauth_consent import consent_query
from tests.fixtures.oauth_resource import exchange_data, service_request


async def delegated(client, access):
    """真实 HTTP 服务交换得到委托，不能注入已验证主体替代认证验收。"""
    result = await client.post("/oauth/token", data=exchange_data(access), headers=dict(service_request({}).headers))
    assert result.status_code == 200, result.text
    return result.json()["access_token"]


async def test_real_delegated_bearer_reuses_whoami_and_scope_guard(oauth_http_client, mcp_access):
    """委托 whoami 保持 PAT 兼容字段为 null，并且不能凭来源扩大 Scope。"""
    client, _, _ = oauth_http_client
    raw = await delegated(client, mcp_access["access_token"])
    headers = {"Authorization": "Bearer " + raw}
    identity = await client.get("/api/v1/auth/whoami", headers=headers)
    assert identity.status_code == 200, identity.text
    body = identity.json()
    assert body["token"] is None and body["credential"]["type"] == "delegated"
    assert body["credential"]["audience"] == POLICY.api_audience
    assert body["credential"]["service_id"] == "mcp-service"
    assert [item["id"] for item in body["workspaces"]] == [1]
    assert raw not in identity.text and mcp_access["access_token"] not in identity.text
    assert identity.headers["cache-control"] == "private, no-store"
    forbidden = await client.get("/api/v1/workspaces", headers=headers)
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "INSUFFICIENT_SCOPE"


@pytest.mark.parametrize("kind", ["access", "refresh", "fake_delegated", "unknown", "disabled", "duplicate"])
async def test_external_api_rejects_wrong_bearer_namespace(oauth_http_client, mcp_access, kind):
    """MCP access/refresh、伪造委托和重复认证头不能落入 PAT 或服务身份回退。"""
    client, _, settings = oauth_http_client
    if kind == "access":
        raw = mcp_access["access_token"]
    elif kind == "refresh":
        raw = mcp_access["refresh_token"]
    else:
        raw = await delegated(client, mcp_access["access_token"]) if kind in {"disabled", "duplicate"} else "wp_dlg_fake" if kind == "fake_delegated" else "unknown"
    if kind == "disabled":
        settings.oauth_enabled = False
    headers = [("Authorization", "Bearer " + raw)]
    if kind == "duplicate":
        headers.append(("Authorization", "Bearer " + raw))
    result = await client.get("/api/v1/auth/whoami", headers=headers)
    assert result.status_code == 401 and result.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("change", ["revoke", "membership", "service", "source"])
async def test_delegated_bearer_rechecks_state_after_issue(oauth_http_client, mcp_access, change):
    """没有放行缓存：已发行委托在授权、成员、服务或源令牌失效后下一请求即失败。"""
    from app.core.time_utils import utc_now

    client, factory, _ = oauth_http_client
    raw = await delegated(client, mcp_access["access_token"])
    headers = {"Authorization": "Bearer " + raw}
    assert (await client.get("/api/v1/auth/whoami", headers=headers)).status_code == 200
    if change == "revoke":
        assert (await client.post("/api/v1/account/oauth/grants/grant-1/revoke")).status_code == 200
    else:
        async with factory() as session:
            if change == "membership":
                await session.execute(update(WorkspaceMember).values(status="inactive"))
            elif change == "service":
                await session.execute(update(OAuthMcpService).values(is_active=False))
            else:
                await session.execute(update(OAuthToken).where(OAuthToken.kind == "access").values(revoked_at=utc_now()))
            await session.commit()
    result = await client.get("/api/v1/auth/whoami", headers=headers)
    assert result.status_code == 401


async def test_full_consent_exchange_and_explicit_workspace_flow(oauth_http_client, mcp_access):
    """从 Cookie 显式批准到真实业务空间读取闭环，之后新增的空间不能自动获得授权。"""
    from app.services.oauth.chatgpt_client import (
        CHATGPT_CLIENT_ID,
        CHATGPT_REDIRECT_URI,
    )

    client, factory, _ = oauth_http_client
    prepared = await client.post("/api/v1/account/oauth/consents", json={
        "authorization_query": consent_query(scope="workspace:read page:read"),
    })
    view = prepared.json()
    confirmed = await client.post(f'/api/v1/account/oauth/consents/{view["request_id"]}/decision', json={
        "csrf_token": view["csrf_token"], "approved": True, "scopes": ["workspace:read", "page:read"], "workspace_ids": [1],
    })
    code = parse_qs(urlsplit(confirmed.json()["redirect_uri"]).query)["code"][0]
    issued = await client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": CHATGPT_CLIENT_ID,
        "redirect_uri": CHATGPT_REDIRECT_URI, "resource": POLICY.mcp_resource,
        "code_verifier": VERIFIER, "code": code,
    })
    access = issued.json()["access_token"]
    exchanged = await client.post("/oauth/token", data=exchange_data(access, scope="workspace:read page:read"), headers=dict(service_request({}).headers))
    assert exchanged.status_code == 200, exchanged.text
    raw = exchanged.json()["access_token"]
    async with factory() as session:
        session.add(Workspace(id=2, code="future", name="后加入空间"))
        await session.flush()
        session.add(WorkspaceMember(workspace_id=2, user_id=1))
        await session.commit()
    headers = {"Authorization": "Bearer " + raw}
    spaces = await client.get("/api/v1/workspaces", headers=headers)
    assert spaces.status_code == 200, spaces.text
    assert [item["id"] for item in spaces.json()] == [1]
    from app.schemas.api_access_token import ApiAccessTokenCreateRequest
    from app.services.api_access_token_service import ApiAccessTokenService

    async with factory() as session:
        pat = await ApiAccessTokenService(session).create_token(user_id=1, payload=ApiAccessTokenCreateRequest(
            name="对拍 PAT", workspace_ids=[1], scopes=["workspace:read", "page:read"],
        ))
    pat_headers = {"Authorization": "Bearer " + pat.token}
    pat_spaces = await client.get("/api/v1/workspaces", headers=pat_headers)
    assert pat_spaces.status_code == 200 and pat_spaces.json() == spaces.json()
    pat_capabilities = await client.get("/api/v1/workspaces/1/capabilities", headers=pat_headers)
    delegated_capabilities = await client.get("/api/v1/workspaces/1/capabilities", headers=headers)
    assert pat_capabilities.status_code == delegated_capabilities.status_code == 200
    assert delegated_capabilities.json() == pat_capabilities.json()
    assert isinstance(delegated_capabilities.json()["operations"], list)
    assert all(isinstance(item, str) for item in delegated_capabilities.json()["operations"])
    forbidden = await client.get("/api/v1/workspaces/2/capabilities", headers={**headers, "X-Workspace-ID": "2"})
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"
