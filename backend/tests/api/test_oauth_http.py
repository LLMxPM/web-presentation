"""文件功能：验证 OAuth 公开端点、登录 Cookie、Origin、发现身份和账户撤销边界。"""

from urllib.parse import parse_qs, urlsplit

import pytest
from app.models.oauth_grant import OAuthGrant

from tests.fixtures.oauth import POLICY
from tests.fixtures.oauth_consent import consent_query

BASE = "/api/v1/account/oauth"


async def test_discovery_and_authorize_use_configured_identity(oauth_http_client):
    """伪造 Host/Forwarded 不能改变发现或 Editor 入口，授权页不会自动批准。"""
    client, _, _ = oauth_http_client
    response = await client.get("/.well-known/oauth-authorization-server", headers={"Host": "attacker.test", "Forwarded": "host=attacker.test;proto=http"})
    data = response.json()
    assert data["issuer"] == POLICY.issuer
    assert data["authorization_endpoint"] == POLICY.issuer + "/oauth/authorize"
    assert data["client_id_metadata_document_supported"] is True
    assert data["authorization_response_iss_parameter_supported"] is True
    assert data["code_challenge_methods_supported"] == ["S256"]
    assert "registration_endpoint" not in data
    result = await client.get("/oauth/authorize?" + consent_query(), follow_redirects=False)
    target = urlsplit(result.headers["location"])
    assert target.scheme + "://" + target.netloc == POLICY.issuer
    assert target.path == "/oauth/consent"
    assert parse_qs(target.query) == {"authorization_query": [consent_query()]}
    assert result.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("query", [
    consent_query() + "&resource=https://attacker.test",
    consent_query(redirect_uri="https://attacker.test"),
    consent_query(client_id="https://attacker.test/client.json"),
])
async def test_authorization_rejects_ambiguous_or_untrusted_requests(oauth_http_client, query):
    """错误回调和重复参数不能变成攻击者重定向，也不能创建确认记录。"""
    client, _, _ = oauth_http_client
    response = await client.get("/oauth/authorize?" + query, follow_redirects=False)
    assert response.status_code in {400, 401}
    assert "location" not in response.headers
    assert "error" in response.json()


async def test_known_error_callback_also_contains_issuer(oauth_http_client):
    """已验证回调上的 invalid_scope 也携带 RFC 9207 iss 和原始 state。"""
    client, _, _ = oauth_http_client
    response = await client.get("/oauth/authorize?" + consent_query(scope="unknown:read"), follow_redirects=False)
    assert response.status_code == 302
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["iss"] == [POLICY.issuer] and params["state"] == ["test-state"]
    assert params["error"] == ["invalid_scope"]


async def test_plain_pkce_cannot_issue_and_returns_safe_error_callback(oauth_http_client):
    """Authlib 可将 PKCE 错误送回已验证回调，仍须拒绝发行并携带 issuer。"""
    client, _, _ = oauth_http_client
    response = await client.get("/oauth/authorize?" + consent_query(code_challenge_method="plain"), follow_redirects=False)
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["error"] == ["invalid_request"] and "code" not in params
    assert params["iss"] == [POLICY.issuer]


async def test_registered_service_uses_http_introspection_and_exchange(oauth_http_client, mcp_access):
    """通过真实 HTTP Basic 表单自省并交换，公开路由不能放宽成熟核心的边界。"""
    from tests.fixtures.oauth_resource import exchange_data, service_request

    client, _, _ = oauth_http_client
    access = mcp_access["access_token"]
    headers = dict(service_request({}).headers)
    inspected = await client.post("/oauth/introspect", data={"token": access}, headers=headers)
    assert inspected.status_code == 200 and inspected.json()["active"] is True
    assert inspected.json()["aud"] == POLICY.mcp_resource
    exchanged = await client.post("/oauth/token", data=exchange_data(access), headers=headers)
    assert exchanged.status_code == 200, exchanged.text
    assert exchanged.json()["access_token"].startswith("wp_dlg_")
    assert "refresh_token" not in exchanged.json()
    client.headers.pop("Authorization", None)
    denied = await client.post("/oauth/introspect", data={"token": access})
    assert denied.status_code in {400, 401} and "error" in denied.json()


@pytest.mark.parametrize("origin", [None, "null", "https://attacker.test"])
async def test_cookie_write_requires_explicit_origin(oauth_http_client, origin):
    """授权和撤销不能以 Referer、Host 或宽泛 CORS 集合替代精确 Editor origin。"""
    client, _, _ = oauth_http_client
    client.headers.pop("Origin")
    if origin is not None:
        client.headers["Origin"] = origin
    response = await client.post(BASE + "/consents", json={"authorization_query": consent_query()})
    assert response.status_code == 403
    assert response.json()["code"] == "OAUTH_ORIGIN_INVALID"
    revoke = await client.post(BASE + "/grants/grant-1/revoke")
    assert revoke.status_code == 403


async def test_account_does_not_accept_token_as_cookie_login(oauth_http_client):
    """账户授权界面只接受平台登录，Bearer 用户令牌不能代替 Cookie。"""
    client, _, _ = oauth_http_client
    client.cookies.clear()
    response = await client.post(BASE + "/consents", json={"authorization_query": consent_query()}, headers={"Authorization": "Bearer wp_oat_fake"})
    assert response.status_code == 401


async def test_list_and_revoke_only_current_users_grant(oauth_http_client):
    """授权列表不返回凭证；本人重复撤销幂等，未知授权无额外信息。"""
    client, factory, _ = oauth_http_client
    listed = await client.get(BASE + "/grants")
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["grant_id"] == "grant-1"
    assert listed.json()["items"][0]["is_active"] is True
    assert "token" not in listed.text
    for _ in range(2):
        assert (await client.post(BASE + "/grants/grant-1/revoke")).status_code == 200
    async with factory() as session:
        assert (await session.get(OAuthGrant, "grant-1")).revoked_at is not None
    listed = await client.get(BASE + "/grants")
    assert listed.json()["items"][0]["is_active"] is False
    assert (await client.post(BASE + "/grants/unknown/revoke")).status_code == 404


async def test_disabled_oauth_is_json_404_and_account_shows_disabled(oauth_http_client):
    """默认关闭不发布发现/发行能力，账户界面得到明确状态。"""
    client, _, settings = oauth_http_client
    settings.oauth_enabled = False
    for path in ["/.well-known/oauth-authorization-server", "/oauth/authorize"]:
        response = await client.get(path)
        assert response.status_code == 404 and response.headers["content-type"].startswith("application/json")
    assert (await client.post("/oauth/token", data={})).status_code == 404
    assert (await client.get(BASE + "/grants")).json() == {"enabled": False, "items": []}


@pytest.mark.parametrize("kind", ["json", "too_large", "duplicates", "query"])
async def test_form_errors_are_standard_oauth_json(oauth_http_client, kind):
    """拒绝非表单、超限、重复和 URL 混合来源，不退回平台错误 envelope。"""
    client, _, _ = oauth_http_client
    if kind == "json":
        response = await client.post("/oauth/token", json={"grant_type": "authorization_code"})
    elif kind == "too_large":
        response = await client.post("/oauth/token", content="x=" + "a" * 16384, headers={"Content-Type": "application/x-www-form-urlencoded"})
    elif kind == "query":
        response = await client.post("/oauth/token?grant_type=refresh_token", data={"grant_type": "authorization_code"})
    else:
        response = await client.post("/oauth/token", content="grant_type=authorization_code&grant_type=refresh_token", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    assert response.headers["cache-control"] == "private, no-store"
