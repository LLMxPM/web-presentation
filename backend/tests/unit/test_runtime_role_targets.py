"""文件功能：验证 Backend 按职责解析 Runtime 内部目标地址并正确回退 runtime_base_url。"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import AppSettings, validate_runtime_role_targets
from app.services.runtime_build_client import RuntimeBuildClient
from app.services.runtime_diagnostics_client import RuntimeDiagnosticsClient
from app.services.runtime_visual_edit_client import RuntimeVisualEditClient


def _settings(**overrides: str) -> AppSettings:
    """构造仅覆盖 Runtime 地址字段的测试配置。"""

    base = {
        "runtime_base_url": "http://runtime:7373",
        "runtime_preview_base_url": "",
        "runtime_build_base_url": "",
        "runtime_check_base_url": "",
    }
    base.update(overrides)
    return AppSettings(**base)  # type: ignore[arg-type]


def test_resolve_runtime_role_base_url_falls_back() -> None:
    """未配置角色地址时三类目标均回退 runtime_base_url。"""

    settings = _settings()
    assert settings.resolve_runtime_role_base_url("preview") == "http://runtime:7373"
    assert settings.resolve_runtime_role_base_url("build") == "http://runtime:7373"
    assert settings.resolve_runtime_role_base_url("check") == "http://runtime:7373"


def test_resolve_runtime_role_base_url_prefers_explicit() -> None:
    """配置了角色地址时优先使用该地址，并去掉末尾斜杠。"""

    settings = _settings(
        runtime_preview_base_url="http://runtime-preview:7373/",
        runtime_build_base_url="http://runtime-build:7373",
        runtime_check_base_url="http://runtime-check:7373/",
    )
    assert settings.resolve_runtime_role_base_url("preview") == "http://runtime-preview:7373"
    assert settings.resolve_runtime_role_base_url("build") == "http://runtime-build:7373"
    assert settings.resolve_runtime_role_base_url("check") == "http://runtime-check:7373"


@pytest.mark.asyncio
async def test_clients_use_role_specific_base_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """构建、诊断、可视化编辑客户端应分别命中 build/check 目标。"""

    captured: list[str] = []

    class _CaptureTransport(httpx.AsyncBaseTransport):
        def __init__(self, label: str) -> None:
            self.label = label

        async def handle_request(self, request: httpx.Request) -> httpx.Response:
            captured.append(f"{self.label}:{request.url.scheme}://{request.url.host}:{request.url.port}")
            return httpx.Response(200, json={"artifact_id": "a", "base_url": "http://x", "message": "ok"})

    settings = _settings(
        runtime_preview_base_url="http://runtime-preview:7373",
        runtime_build_base_url="http://runtime-build:7373",
        runtime_check_base_url="http://runtime-check:7373",
    )
    monkeypatch.setattr(
        "app.services.runtime_build_client.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.services.runtime_diagnostics_client.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.services.runtime_visual_edit_client.get_settings", lambda: settings
    )

    build_client = RuntimeBuildClient()
    # 仅验证地址解析，不真正发起网络调用。
    assert build_client.settings.resolve_runtime_role_base_url("build") == "http://runtime-build:7373"
    diag_client = RuntimeDiagnosticsClient()
    assert diag_client.settings.resolve_runtime_role_base_url("check") == "http://runtime-check:7373"
    visual_client = RuntimeVisualEditClient()
    assert visual_client.settings.resolve_runtime_role_base_url("check") == "http://runtime-check:7373"


def test_validate_runtime_role_targets_rejects_empty() -> None:
    """目标地址为空时启动校验应报错。"""

    settings = _settings(runtime_base_url="")
    with pytest.raises(ValueError):
        validate_runtime_role_targets(settings)


def test_validate_runtime_role_targets_warns_on_preview_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """build/check 目标与 preview 专属地址相同时应输出告警而非报错。"""

    settings = _settings(
        runtime_preview_base_url="http://runtime-preview:7373",
        runtime_build_base_url="http://runtime-preview:7373",
    )
    with caplog.at_level("WARNING"):
        validate_runtime_role_targets(settings)
    assert any("preview" in record.message for record in caplog.records)


def test_validate_runtime_role_targets_accepts_multi_target_lists() -> None:
    """计算角色多副本列表中的每个目标都必须是绝对 http(s) 地址。"""

    settings = _settings(
        runtime_build_base_urls="http://build-1:7373,http://build-2:7373",
        runtime_check_base_urls='["http://check-1:7373","http://check-2:7373"]',
    )
    validate_runtime_role_targets(settings)
    assert settings.resolve_runtime_role_base_urls("build") == [
        "http://build-1:7373",
        "http://build-2:7373",
    ]
    assert settings.resolve_runtime_role_base_urls("check") == [
        "http://check-1:7373",
        "http://check-2:7373",
    ]


def test_validate_runtime_role_targets_rejects_non_http_list_entry() -> None:
    """多副本列表中出现非法协议地址时启动校验应报错。"""

    settings = _settings(runtime_check_base_urls="http://check-1:7373,ftp://bad:7373")
    with pytest.raises(ValueError):
        validate_runtime_role_targets(settings)
