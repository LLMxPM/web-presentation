"""文件功能：验证 ChatGPT CIMD 白名单、配置闭合和 Authlib RFC 9207 回调。"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.core.oauth_config import resolve_oauth_policy
from app.services.oauth import chatgpt_client
from app.services.oauth.chatgpt_client import (
    CHATGPT_CLIENT_ID,
    CHATGPT_REDIRECT_URI,
    fetch_chatgpt_client,
    validate_chatgpt_metadata,
)
from app.services.oauth.protocol import McpAuthorizationServer
from app.services.oauth.request import ProtocolRequest
from authlib.oauth2.rfc6749.errors import InvalidClientError
from authlib.oauth2.rfc7636 import create_s256_code_challenge


def configuration(**changes):
    """使用显式 HTTPS 地址，测试不依赖开发机器环境。"""
    return SimpleNamespace(**{
        "oauth_enabled": True,
        "oauth_issuer": "https://platform.test",
        "oauth_mcp_resource": "https://mcp.test/mcp",
        "oauth_api_audience": "https://platform.test/api/v1",
        "oauth_editor_origin": "https://platform.test",
        "session_secure": True,
        "cors_origins": [],
        **changes,
    })


def metadata(**changes):
    """保留生产文档的数组和旧单值偏好差异，验证不会误选机密认证。"""
    return {
        "client_id": CHATGPT_CLIENT_ID,
        "redirect_uris": [CHATGPT_REDIRECT_URI],
        "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
        "token_endpoint_auth_method": "private_key_jwt",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        **changes,
    }


@pytest.mark.parametrize("changes", [
    {"oauth_issuer": "https://platform.test/"},
    {"oauth_editor_origin": "http://platform.test"},
    {"oauth_editor_origin": "https://unknown.test"},
    {"oauth_editor_origin": "https://platform.test?x=1"},
    {"session_secure": False},
])
def test_enabled_oauth_requires_closed_configuration(changes):
    """不能使用推导 Host、不安全 Cookie 或未准入的 Editor origin。"""
    with pytest.raises(ValueError):
        resolve_oauth_policy(configuration(**changes))


def test_disabled_oauth_does_not_require_production_addresses():
    """保留现有本地开发体验，默认关闭不要求部署参数。"""
    assert resolve_oauth_policy(SimpleNamespace(oauth_enabled=False)) is None


@pytest.mark.parametrize("changes", [
    {"client_id": "https://attacker.test/client.json"},
    {"redirect_uris": [CHATGPT_REDIRECT_URI + "/other"]},
    {"redirect_uris": [CHATGPT_REDIRECT_URI, "https://attacker.test"]},
    {"token_endpoint_auth_methods_supported": ["private_key_jwt"]},
    {"grant_types": ["authorization_code"]},
])
def test_metadata_does_not_expand_registration(changes):
    """服务端受限策略不能被远程元数据改变。"""
    with pytest.raises(InvalidClientError):
        validate_chatgpt_metadata(metadata(**changes), resolve_oauth_policy(configuration()))


@pytest.mark.parametrize("approved", [True, False])
def test_success_and_denied_callback_carry_exact_issuer(approved):
    """同时验证成功和拒绝回调的 state 与 RFC 9207 iss，避免虚假发布支持标志。"""
    policy = resolve_oauth_policy(configuration())
    client = validate_chatgpt_metadata(metadata(), policy)
    server = McpAuthorizationServer(client=client, issuer=policy.issuer)
    request = ProtocolRequest(method="GET", uri=policy.issuer + "/oauth/authorize", pairs={
        "client_id": CHATGPT_CLIENT_ID,
        "redirect_uri": CHATGPT_REDIRECT_URI,
        "response_type": "code",
        "scope": "page:read",
        "state": "original-state",
        "resource": policy.mcp_resource,
        "code_challenge": create_s256_code_challenge("a" * 48),
        "code_challenge_method": "S256",
    }.items())
    grant = server.get_consent_grant(request, end_user=1)
    response = server.create_authorization_response(request, grant_user=1 if approved else None, grant=grant)
    params = parse_qs(urlsplit(response.location).query)
    assert params["iss"] == [policy.issuer]
    assert params["state"] == ["original-state"]
    assert ("code" in params) is approved
    assert ("error" in params) is not approved


async def test_fetch_rejects_redirects_and_unknown_addresses(monkeypatch):
    """禁止 SSRF 和通过 HTTP 跳转改换元数据源。"""
    calls = []

    def handler(request):
        """伪造跳转响应并记录唯一可访问地址。"""
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://attacker.test"})

    original = httpx.AsyncClient
    monkeypatch.setattr(chatgpt_client.httpx, "AsyncClient", lambda **kwargs: original(
        **kwargs, transport=httpx.MockTransport(handler)
    ))
    policy = resolve_oauth_policy(configuration())
    with pytest.raises(InvalidClientError):
        await fetch_chatgpt_client("https://attacker.test", policy)
    assert calls == []
    with pytest.raises(InvalidClientError):
        await fetch_chatgpt_client(CHATGPT_CLIENT_ID, policy)
    assert calls == [CHATGPT_CLIENT_ID]
