"""文件功能：通过真实 HTTP 路由验证隔离开关对预览宿主页和受保护构建浏览的影响。"""

import re
from html import unescape
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from app.core.config import get_settings
from app.services.project_build_artifact_proxy_service import (
    BuildArtifactProxyResult,
    ProjectBuildArtifactProxyService,
)
from app.services.token_service import TokenService

from tests.integration.test_preview_service_token_exchange import (
    _generate_preview_token,
)


@pytest.fixture
def single_address_settings(client, monkeypatch):
    """仅修改本测试进程配置，使用一个局域网 IP 的业务和 Runtime Gateway 入口。"""
    cfg = get_settings()
    monkeypatch.setattr(cfg, "backend_public_base_url", "http://192.168.1.20:8080")
    monkeypatch.setattr(cfg, "runtime_public_base_url", "http://192.168.1.20:8080/runtime")
    monkeypatch.setattr(cfg, "cors_origins", ["http://192.168.1.20:8080"])
    return cfg


@pytest.mark.parametrize("isolation_enabled, expected_status", [(True, 503), (False, 200)])
async def test_single_address_preview_keeps_signed_version_and_token_checks(
    client, single_address_settings, monkeypatch, isolation_enabled, expected_status,
):
    """显式关闭后放行单 IP iframe；版本绑定和无效票据拒绝均沿用正式预览入口。"""
    monkeypatch.setattr(single_address_settings, "preview_origin_isolation_enabled", isolation_enabled)
    original = TokenService.verify_preview_context_token(_generate_preview_token())
    original["runtime_version_fingerprint"] = "1.0.0+lan-release"
    token = TokenService.generate_signed_token(original, expires_in_seconds=300)
    path = f"/preview/artifacts/{original['artifact_id']}"

    response = await client.get(path, params={"token": token}, headers={"Accept": "application/json"})
    assert response.status_code == expected_status
    if isolation_enabled:
        assert response.json()["code"] == "PREVIEW_ORIGIN_NOT_ISOLATED"
    else:
        target = urlsplit(unescape(re.search(r'<iframe[^>]+src="([^"]+)"', response.text).group(1)))
        assert f"{target.scheme}://{target.netloc}{target.path}" == "http://192.168.1.20:8080/runtime/__preview"
        bound = TokenService.verify_preview_context_token(parse_qs(target.query)["token"][0])
        assert bound["artifact_id"] == original["artifact_id"]
        assert bound["runtime_version_fingerprint"] == original["runtime_version_fingerprint"]
        assert bound["exp"] <= original["exp"]
        assert "frame-src http://192.168.1.20:8080" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"

    invalid = await client.get(path, params={"token": "invalid"}, headers={"Accept": "application/json"})
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "PREVIEW_CONTEXT_INVALID"


@pytest.mark.parametrize("isolation_enabled, expected_status", [(True, 503), (False, 200)])
async def test_single_address_build_keeps_access_token_requirement(
    client, single_address_settings, monkeypatch, isolation_enabled, expected_status,
):
    """单 IP 构建 HTML 只在关闭隔离后返回，关闭开关不会放行匿名访问或越界票据。"""
    monkeypatch.setattr(single_address_settings, "preview_origin_isolation_enabled", isolation_enabled)
    read_file = AsyncMock(return_value=BuildArtifactProxyResult(
        content=b"<html>lan build</html>", media_type="text/html", headers={"Cache-Control": "no-store"},
    ))
    monkeypatch.setattr(ProjectBuildArtifactProxyService, "get_artifact_file", read_file)
    base = "http://192.168.1.20:8080/build-artifacts/1/2/"
    token = TokenService.generate_build_access_token(project_id=1, job_id=2, user_id=1, expires_in_seconds=300)

    anonymous = await client.get(base)
    assert anonymous.status_code == 404
    response = await client.get(base, params={"token": token})
    assert response.status_code == expected_status
    if isolation_enabled:
        assert response.json()["code"] == "PREVIEW_ORIGIN_NOT_ISOLATED"
        read_file.assert_not_awaited()
    else:
        assert response.content == b"<html>lan build</html>"
        assert "wp_build_token_1_2" in response.cookies
        read_file.assert_awaited_once()
    assert response.headers["cache-control"] == "no-store"

    wrong_scope = await client.get(base.replace("/1/2/", "/1/3/"), params={"token": token})
    assert wrong_scope.status_code == 404
    assert wrong_scope.json()["code"] == "BUILD_ARTIFACT_ANONYMOUS_DISABLED"
