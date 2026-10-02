"""文件功能：系统设置三层优先级、Safe-Mode 降级防 Crash-Loop 与多副本守卫单元测试。"""

import logging
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.config import (
    AppSettings,
    apply_system_settings_override,
    get_db_settings_cache,
    get_settings,
    get_settings_safe_mode_warnings,
)
from app.core.system_settings_spec import (
    SYSTEM_SETTING_SPECS,
    is_env_overridden,
    safe_mode_convert_value,
)
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.schemas.system_setting import S3TestConnectionRequest
from app.services.system_settings_service import SystemSettingsService


@pytest.fixture(autouse=True)
def _reset_settings_fixture():
    """每次测试前后重置 settings 缓存状态。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_priority_default_constants():
    """测试最低优先级：当无 ENV 且无 DB 覆盖时，采用代码默认常量。"""
    settings = get_settings()
    assert settings.app_timezone == "Asia/Shanghai"
    assert settings.asset_storage_driver == "local"
    assert settings.session_ttl_hours == 24
    assert settings.log_level == "INFO"
    assert settings.ai_enabled is True


def test_priority_db_overrides_default():
    """测试第二优先级：当无 ENV 时，DB 设置正确覆盖默认常量。"""
    db_overrides = {
        "app_timezone": "UTC",
        "session_ttl_hours": 48,
        "log_level": "DEBUG",
        "app_name": "测试页面平台",
    }
    updated = apply_system_settings_override(db_overrides)
    assert updated.app_timezone == "UTC"
    assert updated.session_ttl_hours == 48
    assert updated.log_level == "DEBUG"
    assert updated.app_name == "测试页面平台"

    # get_settings() 也应返回同一实例与最新属性
    active = get_settings()
    assert active.app_timezone == "UTC"
    assert active.session_ttl_hours == 48
    assert active.log_level == "DEBUG"
    assert active.app_name == "测试页面平台"


def test_priority_env_overrides_db(monkeypatch: pytest.MonkeyPatch):
    """测试第一优先级：ENV 存在且非空时，ENV 绝对覆盖 DB，并具备救砖否决权。"""
    # 模拟运维在 ENV 中声明了 APP_TIMEZONE 与 LOG_LEVEL
    monkeypatch.setenv("APP_TIMEZONE", "Europe/London")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    get_settings.cache_clear()

    assert is_env_overridden("app_timezone") is True
    assert is_env_overridden("log_level") is True
    assert is_env_overridden("session_ttl_hours") is False

    # 尝试用 DB 配置覆盖
    db_overrides = {
        "app_timezone": "America/New_York",  # 被 ENV 否决
        "log_level": "ERROR",  # 被 ENV 否决
        "session_ttl_hours": 72,  # 无 ENV，DB 成功生效
    }
    updated = apply_system_settings_override(db_overrides)
    assert updated.app_timezone == "Europe/London"
    assert updated.log_level == "WARNING"
    assert updated.session_ttl_hours == 72


def test_safe_mode_fallback_on_corrupted_db_values(caplog: pytest.LogCaptureFixture):
    """测试 Safe-Mode 防变砖：DB 存在非法脏数据时，记录告警并安全降级为默认值，绝不 Crash-Loop。"""
    corrupted_db_records = {
        "app_timezone": "Mars/Olympus_Mons",  # 非法时区
        "asset_storage_driver": "ftp_storage",  # 不支持的驱动
        "session_ttl_hours": -99,  # 非法数值
        "log_level": "ULTRA_VERBOSE",  # 非法日志等级
        "ai_agent_stream_idle_timeout_seconds": "not_a_number",  # 类型错误
    }

    with caplog.at_level(logging.WARNING):
        # 即使 DB 全是脏数据，apply 也绝不抛出未捕获异常崩溃
        settings = apply_system_settings_override(corrupted_db_records)

    # 验证降级回默认安全值
    assert settings.app_timezone == SYSTEM_SETTING_SPECS["app_timezone"].default_value
    assert settings.asset_storage_driver == SYSTEM_SETTING_SPECS["asset_storage_driver"].default_value
    assert settings.session_ttl_hours == SYSTEM_SETTING_SPECS["session_ttl_hours"].default_value
    assert settings.log_level == SYSTEM_SETTING_SPECS["log_level"].default_value
    assert settings.ai_agent_stream_idle_timeout_seconds == SYSTEM_SETTING_SPECS["ai_agent_stream_idle_timeout_seconds"].default_value

    # 验证生成了详细的 Safe-Mode 警告列表
    warnings = get_settings_safe_mode_warnings()
    assert len(warnings) == 5
    warned_keys = {w["key"] for w in warnings}
    assert warned_keys == {
        "app_timezone",
        "asset_storage_driver",
        "session_ttl_hours",
        "log_level",
        "ai_agent_stream_idle_timeout_seconds",
    }


def test_multi_instance_storage_driver_guard(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """测试多副本集群部署守卫：多 Backend 实例下禁止切换回本地存储（local）。"""
    monkeypatch.setenv("BACKEND_MULTI_INSTANCE", "true")
    get_settings.cache_clear()
    assert get_settings().backend_multi_instance is True

    # 尝试切换为 local 驱动
    with caplog.at_level(logging.WARNING):
        settings = apply_system_settings_override({"asset_storage_driver": "local"})

    # 验证本地存储被守卫拦截，记录告警并保持合法配置
    warnings = get_settings_safe_mode_warnings()
    assert any(w["key"] == "asset_storage_driver" for w in warnings)


@pytest.mark.asyncio
async def test_system_settings_service_dry_run_validation():
    """测试 SystemSettingsService 前置校验：非法输入直接 400 拦截，杜绝脏数据入库。"""
    mock_session = AsyncMock()
    service = SystemSettingsService(mock_session)

    # 1. 未知字段拦截
    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"unknown_field_xyz": 123})
    assert exc_info.value.code == "UNKNOWN_SETTING_KEY"

    # 2. 时区校验失败拦截
    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"app_timezone": "Invalid/Zone"})
    assert exc_info.value.code == "SETTING_VALIDATION_ERROR"

    # 3. 驱动校验失败拦截
    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"asset_storage_driver": "ftp"})
    assert exc_info.value.code == "SETTING_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_system_settings_service_env_lock_immutability(monkeypatch: pytest.MonkeyPatch):
    """测试 SystemSettingsService 对 ENV 锁定的配置禁止通过 Web UI 修改。"""
    monkeypatch.setenv("APP_NAME", "环境变量固定的名称")
    get_settings.cache_clear()

    mock_session = AsyncMock()
    service = SystemSettingsService(mock_session)

    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"app_name": "试图通过UI改名"})
    assert exc_info.value.code == "ENV_OVERRIDDEN_IMMUTABLE"


@pytest.mark.asyncio
async def test_system_settings_service_secret_masking():
    """测试敏感字段（如 S3_ACCESS_KEY）返回掩码，且传入掩码时不覆盖原值。"""
    spec = SYSTEM_SETTING_SPECS["s3_access_key"]
    assert spec.is_secret is True
    assert spec.mask_value("AKIA1234567890ABCDEF") == "AKI******DEF"
    assert spec.mask_value("123456") == "******"
    assert spec.mask_value(None) is None


def test_dynamic_log_level_update():
    """测试日志等级动态热调级：即时修改 root_logger、托管 handler 以及 uvicorn 的日志等级。"""
    from app.core.logging_config import _MANAGED_HANDLER_ATTR, configure_app_logging

    # 先初始化 managed logging
    configure_app_logging(get_settings())

    # 1. 动态切换为 DEBUG
    apply_system_settings_override({"log_level": "DEBUG"})
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    for handler in root.handlers:
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            assert handler.level == logging.DEBUG
    assert logging.getLogger("uvicorn").level == logging.DEBUG

    # 2. 动态切换为 WARNING
    apply_system_settings_override({"log_level": "WARNING"})
    assert root.level == logging.WARNING
    for handler in root.handlers:
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            assert handler.level == logging.WARNING
    assert logging.getLogger("uvicorn").level == logging.WARNING

    # 恢复为默认 INFO
    apply_system_settings_override({"log_level": "INFO"})


def test_dynamic_http_trace_toggle():
    """测试 LLM HTTP Trace 动态热切换：配置变更即时影响 build_llm_http_trace_client 输出。"""
    from app.ai.llm_http_trace import build_llm_http_trace_client
    from app.models.ai_llm import AiLlmConfig, AiLlmProviderConfig

    # 构造测试用的 LLM 配置
    provider_config = AiLlmProviderConfig(
        id=1,
        provider_key="openai",
        name="OpenAI Test",
        base_url="https://api.openai.com/v1",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    llm_config = AiLlmConfig(
        id=1,
        provider_config_id=1,
        provider_config=provider_config,
        model_id="gpt-4o",
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    # 1. 默认或显式为 False 时，trace client 为 None
    apply_system_settings_override({"ai_llm_http_trace_enabled": False})
    assert build_llm_http_trace_client(llm_config) is None

    # 2. 动态开启 trace
    apply_system_settings_override({"ai_llm_http_trace_enabled": True})
    client = build_llm_http_trace_client(llm_config)
    assert client is not None

    # 3. 再次动态关闭 trace
    apply_system_settings_override({"ai_llm_http_trace_enabled": False})
    assert build_llm_http_trace_client(llm_config) is None
