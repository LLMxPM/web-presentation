"""文件功能：验证正常预览入口自动绑定签名版本，并保留 Runtime 拒绝语义与响应身份。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from app.core.exceptions import AppException
from app.services.preview_version_binding import bind_preview_runtime_version
from app.services.token_service import TokenService

from tests.integration.test_preview_service_token_exchange import (
    _generate_preview_token,
)


def _mock_runtime(monkeypatch, responder):
    """只替换对 Runtime 的网络访问，保留真实 Backend 入口与 RSA 签名。"""

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(responder)

    def factory(**kwargs):
        """为内部调用创建隔离传输，不修改已经建立的 ASGI 测试客户端。"""

        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def test_browser_entry_binds_version_in_isolated_frame(authenticated_client, monkeypatch):
    """Backend 仅签发带版本的隔离 iframe，不在业务 origin 代理用户 HTML。"""
    from html import unescape
    import re
    from urllib.parse import urlsplit, parse_qs

    token = _generate_preview_token()
    original = TokenService.verify_preview_context_token(token)
    seen = []

    def runtime(request):
        """只允许受信版本探针；不应再从 Backend 请求用户 HTML。"""
        seen.append(request)
        assert request.url.path == "/__runtime_healthz"
        return httpx.Response(200, json={"runtime_kit_version": "1.0.0", "build_id": "release-a"})

    _mock_runtime(monkeypatch, runtime)
    response = await authenticated_client.get(
        f"/preview/artifacts/{original['artifact_id']}", params={"token": token},
        headers={"x-runtime-preview-context": "untrusted", "cookie": "private-business-cookie", "authorization": "Bearer private"},
    )
    assert response.status_code == 200
    target = urlsplit(unescape(re.search(r'<iframe[^>]+src="([^"]+)"', response.text).group(1)))
    assert target.hostname == "preview.localhost"
    bound = TokenService.verify_preview_context_token(parse_qs(target.query)["token"][0])
    # 重新签发会产生新的 iat / jti：只比较稳定声明，避免跨秒边界造成偶发失败。
    volatile_claims = {"iat", "exp", "jti"}
    assert {key: value for key, value in bound.items() if key not in volatile_claims} == {
        **{key: value for key, value in original.items() if key not in volatile_claims},
        "runtime_version_fingerprint": "1.0.0+release-a",
    }
    assert int(bound["exp"]) <= int(original["exp"])
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "Content-Security-Policy" in response.headers
    assert "private-business-cookie" not in response.text
    assert "cookie" not in seen[0].headers and "authorization" not in seen[0].headers


async def test_bound_preview_keeps_version_without_reprobing(authenticated_client, monkeypatch):
    """已绑定票据不随负载均衡探针重新换版，也不延长原有效期。"""

    claims = TokenService.verify_preview_context_token(_generate_preview_token())
    claims["runtime_version_fingerprint"] = "1.0.0+keep"
    probe = AsyncMock(side_effect=AssertionError("不得重新探测"))
    monkeypatch.setattr(httpx.AsyncClient, "get", probe)
    token = await bind_preview_runtime_version(claims)
    assert TokenService.verify_preview_context_token(token) == claims


async def test_missing_runtime_release_identity_fails_closed(authenticated_client, monkeypatch):
    """旧镜像缺发布身份时明确拒绝，不能把不同版本都默认为同一生产 dev。"""

    _mock_runtime(monkeypatch, lambda _: httpx.Response(200, json={"runtime_kit_version": "1.0.0", "build_id": ""}))
    claims = TokenService.verify_preview_context_token(_generate_preview_token())
    with pytest.raises(AppException) as result:
        await bind_preview_runtime_version(claims)
    assert result.value.code == "RUNTIME_VERSION_UNKNOWN"


async def test_preview_shell_does_not_forward_client_credentials(authenticated_client, monkeypatch):
    """浏览器凭证不得进入 Runtime 网络请求或用户页面，宿主页只有固定桥接脚本。"""
    token = _generate_preview_token()
    artifact_id = TokenService.verify_preview_context_token(token)["artifact_id"]
    received = []

    def runtime(request):
        """记录实际版本探针的请求头。"""
        received.append(request.headers)
        return httpx.Response(200, json={"runtime_kit_version": "1.0.0", "build_id": "release-a"})

    _mock_runtime(monkeypatch, runtime)
    response = await authenticated_client.get(
        f"/preview/artifacts/{artifact_id}", params={"token": token},
        headers={"cookie": "private-cookie", "authorization": "Bearer private-token", "x-workspace-id": "private-workspace"},
    )
    assert response.status_code == 200
    assert received
    assert all(key not in received[0] for key in ("cookie", "authorization", "x-workspace-id"))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert all(secret not in response.text for secret in ("private-cookie", "private-token", "private-workspace"))
