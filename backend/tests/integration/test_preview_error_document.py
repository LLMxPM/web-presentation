"""文件功能：验证预览入口的 HTML 错误兜底、JSON 兼容、宿主通知与受信工作台导航。"""

from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from fastapi import Request

from app.api.routes import preview
from app.api import preview_error_response
from app.core.exceptions import AppException
from tests.integration.test_preview_service_token_exchange import _generate_preview_token


@pytest.mark.parametrize("public_url, origins, referer, expected", [
    ("http://127.0.0.1:8080", ["http://127.0.0.1:8080"], "", "http://127.0.0.1:8080/"),
    ("https://api.example.com", ["https://editor.example.com"], "https://api.example.com/preview/x", "https://editor.example.com/"),
    ("https://api.example.com", ["https://editor.example.com"], "https://evil.example/", "https://editor.example.com/"),
])
def test_workbench_exit_follows_deployment_origins(
    monkeypatch: pytest.MonkeyPatch, public_url: str, origins: list[str], referer: str, expected: str,
) -> None:
    """网关单源、独立 API 域名与伪造来源都应返回配置允许的 Editor 入口。"""

    monkeypatch.setattr(preview_error_response, "get_settings", lambda: SimpleNamespace(
        backend_public_base_url=public_url, cors_origins=origins,
    ))
    request = Request({"type": "http", "headers": [(b"referer", referer.encode())]})
    assert preview_error_response.preview_workbench_url(request, {}) == expected


@pytest.mark.parametrize("accept", ["application/json", "*/*", "text/html;q=0", "application/json, text/html;q=0.5"])
async def test_invalid_preview_keeps_json_contract(client: AsyncClient, accept: str) -> None:
    """非文档请求继续返回原始 401/code/message，不通过内容协商放宽鉴权。"""

    response = await client.get("/preview/artifacts/rt_invalid", params={"token": "invalid"}, headers={"Accept": accept})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"code": "PREVIEW_CONTEXT_INVALID", "message": "预览上下文令牌非法或已过期。"}


async def test_invalid_preview_returns_safe_html(client: AsyncClient) -> None:
    """非法票据显示失效而非过期，不泄露 token，也不从未验签信息生成项目导航。"""

    response = await client.get(
        "/preview/artifacts/rt_invalid", params={"token": "secret-invalid-token"},
        headers={"Accept": "text/html", "Referer": "https://untrusted.example/workspaces/99"},
    )
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Accept"
    assert "预览链接已失效" in response.text
    assert "预览链接已过期" not in response.text
    assert "返回工作台" in response.text
    assert "page-preview:error" in response.text
    assert "component-preview:error" in response.text
    assert '"artifactId": "rt_invalid"' in response.text
    assert "secret-invalid-token" not in response.text
    assert "untrusted.example" not in response.text


async def test_missing_preview_token_keeps_validation_status(client: AsyncClient) -> None:
    """缺失参数的浏览器请求也有操作出口，机器请求仍保持原 422 校验契约。"""

    html = await client.get("/preview/artifacts/rt_missing", headers={"Accept": "text/html"})
    assert html.status_code == 422
    assert "PREVIEW_CONTEXT_REQUIRED" in html.text
    assert "返回工作台" in html.text
    api = await client.get("/preview/artifacts/rt_missing", headers={"Accept": "application/json"})
    assert api.status_code == 422
    assert api.json()["code"] == "VALIDATION_ERROR"


async def test_expired_preview_uses_only_verified_navigation(client: AsyncClient) -> None:
    """已过期且签名仍可信的票据仅提供原工作台入口，不延长有效期或直接重建项目。"""

    token = _generate_preview_token(artifact_id="rt_expired", expires_in_seconds=-30)
    response = await client.get(
        "/preview/artifacts/rt_expired", params={"token": token},
        headers={"Accept": "text/html", "Referer": "http://127.0.0.1:5173/workspaces/1/home"},
    )
    assert response.status_code == 401
    assert "预览链接已过期" in response.text
    assert 'href="http://127.0.0.1:5173/workspaces/1/projects/1/pages"' in response.text
    assert token not in response.text


async def test_reload_on_local_backend_keeps_editor_exit(client: AsyncClient) -> None:
    """本地 Backend 上刷新错误页后仍返回 Editor，避免把 Backend 根路径当成工作台。"""

    response = await client.get(
        "/preview/artifacts/rt_invalid", params={"token": "invalid"},
        headers={"Accept": "text/html", "Referer": "http://127.0.0.1:8000/preview/artifacts/rt_invalid"},
    )
    assert response.status_code == 401
    assert 'href="http://127.0.0.1:5173/"' in response.text


async def test_artifact_mismatch_preserves_machine_error(client: AsyncClient) -> None:
    """artifact 不匹配继续拒绝，并按载体提供错误响应。"""

    token = _generate_preview_token(artifact_id="rt_original")
    for accept in ("application/json", "text/html"):
        response = await client.get("/preview/artifacts/rt_other", params={"token": token}, headers={"Accept": accept})
        assert response.status_code == 403
        if accept == "application/json":
            assert response.json() == {"detail": "PREVIEW_ARTIFACT_MISMATCH"}
        else:
            assert "PREVIEW_ARTIFACT_MISMATCH" in response.text
            assert "/projects/1/pages" not in response.text


async def test_runtime_failure_notifies_host_without_runtime_js(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime 版本探测或代理失败也应立即通知宿主，避免只修复 token 分支。"""

    monkeypatch.setattr(preview, "bind_preview_runtime_version", AsyncMock(side_effect=AppException(
        status_code=502, code="RUNTIME_VERSION_UNAVAILABLE", detail="Runtime 不可用。",
    )))
    token = _generate_preview_token()
    response = await client.get(
        "/preview/artifacts/artifact-exchange-1", params={"token": token}, headers={"Accept": "text/html"},
    )
    assert response.status_code == 502
    assert "预览暂时无法打开" in response.text
    assert "RUNTIME_VERSION_UNAVAILABLE" in response.text
    assert "page-preview:error" in response.text
    assert "重试加载" in response.text
