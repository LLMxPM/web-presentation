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


async def test_browser_entry_binds_signed_version_and_preserves_skew_response(authenticated_client, monkeypatch):
    """浏览器无需自填期望头；HTML 子票据保留 exp/权限，409 与版本响应透传。"""

    token = _generate_preview_token()
    original = TokenService.verify_preview_context_token(token)
    seen = []

    def runtime(request):
        """模拟版本探针后命中另一副本，必须显式拒绝而不能返回静默混版页面。"""

        if request.url.path == "/__runtime_healthz":
            return httpx.Response(200, json={"runtime_kit_version": "1.0.0", "build_id": "release-a"})
        bound = TokenService.verify_preview_context_token(request.headers["x-runtime-preview-context"])
        seen.append(bound)
        assert request.headers["x-expected-runtime-version-fingerprint"] == "1.0.0+release-a"
        return httpx.Response(409, content="PREVIEW_VERSION_SKEW", headers={
            "Content-Type": "text/html", "x-runtime-version-fingerprint": "1.0.0+release-b",
        })

    _mock_runtime(monkeypatch, runtime)
    response = await authenticated_client.get(
        f"/preview/artifacts/{original['artifact_id']}", params={"token": token},
        headers={"x-expected-runtime-version-fingerprint": "untrusted-browser-value"},
    )
    assert response.status_code == 409
    assert response.headers["x-runtime-version-fingerprint"] == "1.0.0+release-b"
    assert response.headers["cache-control"] == "no-store"
    assert seen[0] == {**original, "runtime_version_fingerprint": "1.0.0+release-a"}


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
