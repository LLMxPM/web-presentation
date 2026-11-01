"""文件功能：验证预览隔离的默认拒绝策略、环境开关与单地址预览及构建地址解析。"""

import pytest
from app.core.config import AppSettings
from app.core.exceptions import AppException
from app.services import preview_origin_service as origin_service


@pytest.mark.parametrize("business_source", ["backend", "cors"])
def test_isolation_is_enabled_by_default(monkeypatch, business_source):
    """缺省开关时，Backend 或业务 CORS 使用的主机名都不能执行预览代码。"""
    monkeypatch.delenv("PREVIEW_ORIGIN_ISOLATION_ENABLED", raising=False)
    cfg = AppSettings(
        backend_public_base_url="http://192.168.1.20:8080" if business_source == "backend" else "http://backend:8000",
        cors_origins=["http://192.168.1.20:8080"],
        runtime_public_base_url="http://192.168.1.20:8080/runtime",
    )
    monkeypatch.setattr(origin_service, "get_settings", lambda: cfg)

    assert cfg.preview_origin_isolation_enabled is True
    with pytest.raises(AppException) as error:
        origin_service.isolated_preview_base_url()
    assert error.value.status_code == 503
    assert error.value.code == "PREVIEW_ORIGIN_NOT_ISOLATED"


@pytest.mark.parametrize("hostname", ["192.168.1.20", "localhost", "127.0.0.1", "[::1]"])
def test_disabled_isolation_keeps_configured_host_and_path(monkeypatch, hostname):
    """环境变量关闭隔离后，局域网和回环地址均不拒绝或改写，构建地址复用相同策略。"""
    monkeypatch.setenv("PREVIEW_ORIGIN_ISOLATION_ENABLED", "false")
    base = f"http://{hostname}:8080"
    cfg = AppSettings(backend_public_base_url=base, runtime_public_base_url=f"{base}/runtime/")
    monkeypatch.setattr(origin_service, "get_settings", lambda: cfg)

    assert cfg.preview_origin_isolation_enabled is False
    assert origin_service.isolated_preview_base_url() == f"{base}/runtime"
    assert origin_service.isolated_preview_origin() == base
    response = origin_service.preview_shell(artifact_id="rt_lan", token="ticket", workbench_url=base)
    assert f'src="{base}/runtime/__preview?token=ticket"'.encode() in response.body
    assert f"frame-src {base}" in response.headers["Content-Security-Policy"]
    assert b"event.source === frame.contentWindow && event.origin === runtimeOrigin" in response.body


def test_isolation_can_be_reenabled_by_environment(monkeypatch):
    """环境变量重新开启隔离后恢复本地改写及远程同主机名拒绝。"""
    monkeypatch.setenv("PREVIEW_ORIGIN_ISOLATION_ENABLED", "true")
    cfg = AppSettings(backend_public_base_url="http://localhost:8080", runtime_public_base_url="http://localhost:8080/runtime")
    monkeypatch.setattr(origin_service, "get_settings", lambda: cfg)
    assert origin_service.isolated_preview_base_url() == "http://preview.localhost:8080/runtime"

    cfg.backend_public_base_url = "http://192.168.1.20:8080"
    cfg.runtime_public_base_url = "http://192.168.1.20:8080/runtime"
    with pytest.raises(AppException):
        origin_service.isolated_preview_base_url()


def test_disabled_isolation_preserves_independent_runtime_and_internal_fallback(monkeypatch):
    """开关不替部署者重选源站，独立预览地址和缺省公开地址时的内部回退均保持原值。"""
    cfg = AppSettings(
        preview_origin_isolation_enabled=False,
        backend_public_base_url="http://192.168.1.20:8080",
        runtime_public_base_url="http://preview.home.arpa:8080/runtime",
        runtime_base_url="http://runtime:7373",
    )
    monkeypatch.setattr(origin_service, "get_settings", lambda: cfg)
    assert origin_service.isolated_preview_base_url() == "http://preview.home.arpa:8080/runtime"
    cfg.runtime_public_base_url = None
    assert origin_service.isolated_preview_base_url() == "http://runtime:7373"
