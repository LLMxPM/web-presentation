"""文件功能：验证 Backend 按职责解析 Runtime 内部目标地址并正确回退 runtime_base_url。"""

from __future__ import annotations

import pytest

from app.core.config import AppSettings, validate_runtime_role_targets
from app.services.runtime_diagnostics_client import RuntimeDiagnosticsClient
from app.services.runtime_visual_edit_client import RuntimeVisualEditClient


def _settings(**overrides: str) -> AppSettings:
    """构造仅覆盖 Runtime 地址字段的测试配置。"""

    base = {
        "runtime_base_url": "http://runtime:7373",
        "runtime_preview_base_url": "",
        "runtime_check_base_url": "",
    }
    base.update(overrides)
    return AppSettings(**base)  # type: ignore[arg-type]


def test_resolve_runtime_role_base_url_falls_back() -> None:
    """未配置角色地址时 preview 与 check 目标均回退 runtime_base_url。"""

    settings = _settings()
    assert settings.resolve_runtime_role_base_url("preview") == "http://runtime:7373"
    assert settings.resolve_runtime_role_base_url("check") == "http://runtime:7373"


def test_resolve_runtime_role_base_url_prefers_explicit() -> None:
    """配置了角色地址时优先使用该地址，并去掉末尾斜杠。"""

    settings = _settings(
        runtime_preview_base_url="http://runtime-preview:7373/",
        runtime_check_base_url="http://runtime-check:7373/",
    )
    assert settings.resolve_runtime_role_base_url("preview") == "http://runtime-preview:7373"
    assert settings.resolve_runtime_role_base_url("check") == "http://runtime-check:7373"


def test_light_role_shares_check_targets() -> None:
    """轻量工具与诊断共用计算目标，但准入独立计数。"""

    settings = _settings(runtime_check_base_urls="http://check-1:7373,http://check-2:7373")
    assert settings.resolve_runtime_role_base_url("light") == "http://check-1:7373"
    assert settings.resolve_runtime_role_base_urls("light") == ["http://check-1:7373", "http://check-2:7373"]


def test_clients_use_role_specific_base_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """诊断与可视化编辑客户端应命中 check 目标。"""

    settings = _settings(
        runtime_preview_base_url="http://runtime-preview:7373",
        runtime_check_base_url="http://runtime-check:7373",
    )
    monkeypatch.setattr(
        "app.services.runtime_diagnostics_client.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "app.services.runtime_visual_edit_client.get_settings", lambda: settings
    )

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
    """check 目标与 preview 专属地址相同时应输出告警而非报错。"""

    settings = _settings(
        runtime_preview_base_url="http://runtime-preview:7373",
        runtime_check_base_url="http://runtime-preview:7373",
    )
    with caplog.at_level("WARNING"):
        validate_runtime_role_targets(settings)
    assert any("preview" in record.message for record in caplog.records)


def test_validate_runtime_role_targets_accepts_multi_target_lists() -> None:
    """计算角色多副本列表中的每个目标都必须是绝对 http(s) 地址。"""

    settings = _settings(runtime_check_base_urls='["http://check-1:7373","http://check-2:7373"]')
    validate_runtime_role_targets(settings)
    assert settings.resolve_runtime_role_base_urls("check") == [
        "http://check-1:7373",
        "http://check-2:7373",
    ]


def test_validate_runtime_role_targets_rejects_non_http_list_entry() -> None:
    """多副本列表中出现非法协议地址时启动校验应报错。"""

    settings = _settings(runtime_check_base_urls="http://check-1:7373,ftp://bad:7373")
    with pytest.raises(ValueError):
        validate_runtime_role_targets(settings)


@pytest.mark.parametrize(
    "retired_env",
    [
        "RUNTIME_BUILD_BASE_URL",
        "RUNTIME_BUILD_BASE_URLS",
        "RUNTIME_BUILD_MAX_INFLIGHT",
        "RUNTIME_BUILD_REQUEST_TIMEOUT_SECONDS",
        "PROJECT_BUILD_QUEUE_CONCURRENCY",
    ],
)
def test_retired_build_dispatch_env_is_rejected(monkeypatch: pytest.MonkeyPatch, retired_env: str) -> None:
    """Backend 主动派发构建的配置已删除，残留键必须启动失败而不是静默忽略。"""

    monkeypatch.setenv(retired_env, "1")
    with pytest.raises(ValueError, match="已废弃的 Backend 构建派发配置"):
        _settings()
