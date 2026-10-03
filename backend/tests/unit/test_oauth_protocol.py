"""文件功能：验证 Authlib 框架无关协议核的 PKCE、回调、资源、刷新与脱敏边界。"""

from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from app.core.security import hash_password
from app.core.time_utils import utc_now
from app.services.oauth.protocol import McpAuthorizationServer, credential_digest
from app.services.oauth.request import ProtocolRequest
from app.services.oauth.snapshots import ClientSnapshot, CredentialSnapshot
from authlib.oauth2.rfc6749.errors import OAuth2Error
from authlib.oauth2.rfc7636 import create_s256_code_challenge

RESOURCE = "https://mcp.example.test/mcp"
REDIRECT = "https://client.example.test/callback"
VERIFIER = "a" * 48
SCOPES = frozenset({"page:read", "page:write"})


def registered_client(**changes) -> ClientSnapshot:
    """构造显式注册客户端，不使用公开动态注册。"""
    return replace(ClientSnapshot("desktop", (REDIRECT,), SCOPES, RESOURCE), **changes)


def credential(raw: str, **changes) -> CredentialSnapshot:
    """模拟异步查询层提供的未撤销凭证快照。"""
    return replace(
        CredentialSnapshot(
            credential_digest(raw),
            "grant-1",
            "desktop",
            1,
            RESOURCE,
            SCOPES,
            utc_now() + timedelta(minutes=1),
            redirect_uri=REDIRECT,
            code_challenge=create_s256_code_challenge(VERIFIER),
            code_challenge_method="S256",
        ),
        **changes,
    )


def protocol_request(
    data: dict[str, str], *, method="POST", extra=(), headers=None
) -> ProtocolRequest:
    """模拟 FastAPI 已读取表单；重复项保留到协议验证。"""
    return ProtocolRequest(
        method=method,
        uri="https://platform.example.test/oauth/token",
        pairs=[*data.items(), *extra],
        headers=headers,
    )


def code_request(**changes) -> ProtocolRequest:
    """生成绑定回调、资源与 S256 的授权码兑换。"""
    data = {
        "grant_type": "authorization_code",
        "client_id": "desktop",
        "code": "original-code",
        "redirect_uri": REDIRECT,
        "resource": RESOURCE,
        "code_verifier": VERIFIER,
    }
    data.update(changes)
    return protocol_request(data)


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"code_verifier": "b" * 48}, "invalid_grant"),
        ({"redirect_uri": REDIRECT + "/other"}, "invalid_grant"),
        ({"resource": "https://platform.example.test/api/v1"}, "invalid_grant"),
        ({"scope": "page:read page:write asset:read"}, "invalid_scope"),
        ({"client_id": "unregistered"}, "invalid_client"),
    ],
)
def test_code_rejects_invalid_binding_before_consumption(changes, error) -> None:
    """错误的协议绑定不登记消费或生成凭证，原始授权码仍可正确兑换。"""
    server = McpAuthorizationServer(
        client=registered_client(), credential=credential("original-code")
    )
    response = server.token_response(code_request(**changes))
    assert response.body["error"] == error
    assert server.consumed_hash is None and server.pending_token is None
    response = server.token_response(code_request())
    assert response.status_code == 200
    assert server.consumed_hash == credential_digest("original-code")


@pytest.mark.parametrize(
    "extra",
    [
        ("grant_type", "refresh_token"),
        ("resource", RESOURCE),
        ("code_verifier", VERIFIER),
        ("client_id", "other"),
    ],
)
def test_duplicate_token_parameters_fail_closed(extra) -> None:
    """参数重复不能因提前 dict 化而绕过验证。"""
    request = code_request()
    request = protocol_request(request.payload.data, extra=[extra])
    server = McpAuthorizationServer(
        client=registered_client(), credential=credential("original-code")
    )
    assert server.token_response(request).body["error"] == "invalid_request"
    assert server.pending_token is None


@pytest.mark.parametrize(
    "changes",
    [
        {"code_challenge": ""},
        {"code_challenge_method": "plain"},
        {"resource": "https://evil.test/mcp"},
        {"redirect_uri": "https://evil.test/cb"},
        {"redirect_uri": ""},
    ],
)
def test_authorization_requires_exact_redirect_resource_and_s256(changes) -> None:
    """在进入用户确认页前拒绝不安全授权参数。"""
    data = {
        "response_type": "code",
        "client_id": "desktop",
        "redirect_uri": REDIRECT,
        "resource": RESOURCE,
        "scope": "page:read",
        "code_challenge": create_s256_code_challenge(VERIFIER),
        "code_challenge_method": "S256",
        "state": "original-state",
    }
    data.update(changes)
    server = McpAuthorizationServer(client=registered_client())
    with pytest.raises(OAuth2Error):
        server.get_consent_grant(protocol_request(data, method="GET"), end_user=1)
    assert server.pending_code is None


def test_authorization_state_and_code_are_only_staged() -> None:
    """Authlib 生成标准重定向并保留 state，交付之前仍需授权事务提交。"""
    data = {
        "response_type": "code",
        "client_id": "desktop",
        "redirect_uri": REDIRECT,
        "resource": RESOURCE,
        "scope": "page:read",
        "code_challenge": create_s256_code_challenge(VERIFIER),
        "code_challenge_method": "S256",
        "state": "特殊值 + &",
    }
    server = McpAuthorizationServer(client=registered_client())
    request = protocol_request(data, method="GET")
    grant = server.get_consent_grant(request, end_user=1)
    response = server.create_authorization_response(request, grant_user=1, grant=grant)
    query = parse_qs(urlsplit(dict(response.headers)["Location"]).query)
    assert response.status_code == 302
    assert query["state"] == [data["state"]]
    assert query["code"] == [server.pending_code]


def test_refresh_rotation_subset_and_replay_identity() -> None:
    """刷新缩小权限并发行下一代；重放标志必须来自同一已认证客户端。"""
    original = credential("original-refresh", family_id="family-1")
    data = {
        "grant_type": "refresh_token",
        "client_id": "desktop",
        "refresh_token": "original-refresh",
        "resource": RESOURCE,
        "scope": "page:read",
    }
    server = McpAuthorizationServer(client=registered_client(), credential=original)
    response = server.token_response(protocol_request(data))
    assert response.status_code == 200
    assert response.body["scope"] == "page:read"
    assert response.body["refresh_token"] != "original-refresh"
    assert server.consumed_hash == original.credential_hash
    server = McpAuthorizationServer(
        client=registered_client(), credential=replace(original, consumed=True)
    )
    assert (
        server.token_response(protocol_request(data)).body["error"] == "invalid_grant"
    )
    assert server.replayed_refresh_hash == original.credential_hash
    server = McpAuthorizationServer(
        client=registered_client(client_id="other"),
        credential=replace(original, consumed=True),
    )
    data["client_id"] = "other"
    assert (
        server.token_response(protocol_request(data)).body["error"] == "invalid_grant"
    )
    assert server.replayed_refresh_hash is None


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"scope": "asset:read"}, "invalid_scope"),
        ({"resource": "https://other.test/mcp"}, "invalid_grant"),
    ],
)
def test_refresh_cannot_expand_authority(changes, error) -> None:
    """刷新不得扩大原始凭证权限或转移 audience。"""
    data = {
        "grant_type": "refresh_token",
        "client_id": "desktop",
        "refresh_token": "original-refresh",
        "resource": RESOURCE,
    }
    data.update(changes)
    server = McpAuthorizationServer(
        client=registered_client(), credential=credential("original-refresh")
    )
    assert server.token_response(protocol_request(data)).body["error"] == error
    assert server.pending_token is None and server.consumed_hash is None


def test_confidential_client_and_debug_logging_do_not_expose_secrets(caplog) -> None:
    """机密客户端只能用 Basic；库 DEBUG 日志不泄露发行 Token。"""
    import base64
    import logging

    secret = "secret-value"
    client = registered_client(
        auth_method="client_secret_basic", secret_hash=hash_password(secret)
    )
    server = McpAuthorizationServer(
        client=client, credential=credential("original-code")
    )
    caplog.set_level(logging.DEBUG, logger="authlib")
    headers = {
        "authorization": "Basic "
        + base64.b64encode(f"desktop:{secret}".encode()).decode()
    }
    request = code_request()
    response = server.token_response(
        protocol_request(request.payload.data, headers=headers)
    )
    assert response.status_code == 200
    for raw in (response.body["access_token"], response.body["refresh_token"], secret):
        assert raw not in caplog.text
        assert raw not in repr(response)
    assert "no-store" in dict(response.headers)["Cache-Control"]


def test_expired_code_has_no_issuance() -> None:
    """即使哈希和 PKCE 匹配也拒绝过期授权码。"""
    server = McpAuthorizationServer(
        client=registered_client(),
        credential=credential(
            "original-code", expires_at=utc_now() - timedelta(seconds=1)
        ),
    )
    assert server.token_response(code_request()).body["error"] == "invalid_grant"
    assert server.pending_token is None


def test_public_client_cannot_ignore_an_authorization_header() -> None:
    """携带 Basic 的请求不得退回公开客户端 none 认证而忽略错误凭证。"""
    server = McpAuthorizationServer(
        client=registered_client(), credential=credential("original-code")
    )
    request = code_request()
    response = server.token_response(
        protocol_request(
            request.payload.data, headers={"Authorization": "Basic broken"}
        )
    )
    assert response.body["error"] == "invalid_client"
    assert server.pending_token is None
