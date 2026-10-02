"""文件功能：系统设置三层优先级、Safe-Mode 降级防 Crash-Loop 与多副本守卫单元测试。"""

import logging
from pathlib import Path
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
def _reset_settings_fixture(monkeypatch: pytest.MonkeyPatch):
    """每次测试前后重置 settings 缓存状态，并隔离本地开发环境 .env 文件对单元测试的污染。"""
    monkeypatch.setattr("app.core.config._iter_settings_env_files", lambda: [])
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

    # 先初始化为 s3 驱动
    apply_system_settings_override({
        "asset_storage_driver": "s3",
        "s3_bucket": "test-bucket",
        "s3_access_key": "AKTEST",
        "s3_secret_key": "SKTEST",
    })
    assert get_settings().asset_storage_driver == "s3"

    # 尝试切换为 local 驱动
    with caplog.at_level(logging.WARNING):
        settings = apply_system_settings_override({"asset_storage_driver": "local"})

    # 验证本地存储被守卫拦截，记录告警且当前生效驱动依然保持 s3
    assert settings.asset_storage_driver == "s3"
    assert get_settings().asset_storage_driver == "s3"
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
    """测试 SystemSettingsService 对 ENV 锁定的配置禁止通过 Web UI 篡改。"""
    monkeypatch.setenv("APP_NAME", "环境变量固定的名称")
    get_settings.cache_clear()

    mock_session = AsyncMock()
    service = SystemSettingsService(mock_session)

    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"app_name": "试图通过UI改名"})
    assert exc_info.value.code == "ENV_OVERRIDDEN_IMMUTABLE"


@pytest.mark.asyncio
async def test_system_settings_service_env_lock_allows_idempotent_submission(monkeypatch: pytest.MonkeyPatch):
    """测试 SystemSettingsService 对全量表单中未变动的 ENV 锁定配置幂等放行。"""
    monkeypatch.setenv("APP_NAME", "环境变量固定的名称")
    get_settings.cache_clear()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result
    service = SystemSettingsService(mock_session)

    # 传入与当前环境变量相同的值（如前端全量提交）
    res = await service.update_settings({
        "app_name": "环境变量固定的名称",
        "session_ttl_hours": 48,
    })
    assert res is not None


def test_priority_dotenv_overrides_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试 .env 配置文件声明的优先级高于 DB（支持运维改 .env 救砖）。"""
    fake_env = tmp_path / ".env"
    fake_env.write_text("APP_TIMEZONE=Europe/Rome\nLOG_LEVEL=ERROR\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config._iter_settings_env_files", lambda: [fake_env])
    get_settings.cache_clear()

    assert is_env_overridden("app_timezone") is True
    assert is_env_overridden("log_level") is True
    assert is_env_overridden("session_ttl_hours") is False

    # 尝试用 DB 覆盖
    updated = apply_system_settings_override({
        "app_timezone": "America/New_York",
        "log_level": "DEBUG",
        "session_ttl_hours": 72,
    })
    # app_timezone 和 log_level 被 .env 锁死，保持 Europe/Rome 与 ERROR
    assert updated.app_timezone == "Europe/Rome"
    assert updated.log_level == "ERROR"
    # session_ttl_hours 未在 .env 声明，DB 成功生效
    assert updated.session_ttl_hours == 72


@pytest.mark.asyncio
async def test_system_settings_service_rejects_incomplete_s3():
    """测试切为 S3 存储但未提供完整凭证时拒绝保存。"""
    mock_session = AsyncMock()
    service = SystemSettingsService(mock_session)

    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"asset_storage_driver": "s3", "s3_bucket": ""})
    assert exc_info.value.code == "S3_CONFIG_INCOMPLETE"


def test_ai_image_transport_mode_values_and_aliases():
    """测试 ai_image_transport_mode 支持 auto, url, base64 并将 s3/data_url 别名平滑映射。"""
    spec = SYSTEM_SETTING_SPECS["ai_image_transport_mode"]
    assert spec.validator("auto") == "auto"
    assert spec.validator("url") == "url"
    assert spec.validator("base64") == "base64"
    # 别名映射
    assert spec.validator("s3") == "url"
    assert spec.validator("data_url") == "base64"
    with pytest.raises(ValueError):
        spec.validator("invalid_mode")


@pytest.mark.asyncio
async def test_system_settings_service_secret_masking():
    """测试敏感字段（如 S3_ACCESS_KEY）返回掩码，且传入掩码时不覆盖原值。"""
    spec = SYSTEM_SETTING_SPECS["s3_access_key"]
    assert spec.is_secret is True
    assert spec.mask_value("AKIA1234567890ABCDEF") == "******"
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

def test_validate_bool_strict():
    """测试布尔校验器严格模式：拒绝非法未知文本（如 flase），支持合法布尔文本。"""
    spec = SYSTEM_SETTING_SPECS["ai_llm_http_trace_enabled"]
    # 合法真值
    assert spec.validator(True) is True
    assert spec.validator("true") is True
    assert spec.validator("1") is True
    assert spec.validator("yes") is True
    assert spec.validator("on") is True
    assert spec.validator(1) is True

    # 合法假值
    assert spec.validator(False) is False
    assert spec.validator("false") is False
    assert spec.validator("0") is False
    assert spec.validator("no") is False
    assert spec.validator("off") is False
    assert spec.validator("") is False
    assert spec.validator(0) is False

    # 非法字符串与类型必须抛出 ValueError，触发 Safe-Mode 降级
    with pytest.raises(ValueError):
        spec.validator("flase")
    with pytest.raises(ValueError):
        spec.validator("invalid_value")
    with pytest.raises(ValueError):
        spec.validator(2)
    with pytest.raises(ValueError):
        spec.validator([])


def test_dotenv_export_syntax_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试 .env 文件支持 export APP_TIMEZONE=... 语法。"""
    fake_env = tmp_path / ".env"
    fake_env.write_text("export APP_TIMEZONE=Europe/Rome\nexport LOG_LEVEL=ERROR\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config._iter_settings_env_files", lambda: [fake_env])
    get_settings.cache_clear()

    assert is_env_overridden("app_timezone") is True
    assert is_env_overridden("log_level") is True
    assert is_env_overridden("session_ttl_hours") is False


@pytest.mark.asyncio
async def test_reject_clearing_s3_credentials_even_without_driver():
    """测试即便未在 updates 中传入 asset_storage_driver，只要最终生效为 S3 且试图清空必需凭据即刻拦截。"""
    # 先设置当前环境为 S3
    apply_system_settings_override({
        "asset_storage_driver": "s3",
        "s3_bucket": "my-bucket",
        "s3_access_key": "AK123",
        "s3_secret_key": "SK456",
    })
    assert get_settings().asset_storage_driver == "s3"

    mock_session = AsyncMock()
    service = SystemSettingsService(mock_session)

    # 仅提交清空 s3_bucket，未包含 asset_storage_driver
    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"s3_bucket": ""})
    assert exc_info.value.code == "S3_CONFIG_INCOMPLETE"

    # 仅提交清空 s3_secret_key
    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"s3_secret_key": ""})
    assert exc_info.value.code == "S3_CONFIG_INCOMPLETE"


def test_ai_secret_encryption_key_preserved_on_hot_reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试热更新任意配置时，启动期解析的 AI 加密密钥保持不被冲掉。"""
    monkeypatch.delenv("AI_SECRET_ENCRYPTION_KEY", raising=False)
    fake_key = "dGVzdF9mZXJuZXRfa2V5XzMyX2J5dGVzX2xvbmdfMTIzNDU2Nzg="
    # 模拟启动期已持有单实例密钥
    settings = get_settings()
    settings.ai_secret_encryption_key = fake_key
    assert get_settings().ai_secret_encryption_key == fake_key

    # 热更新 unrelated key
    updated = apply_system_settings_override({"app_name": "新名称"})
    assert updated.app_name == "新名称"
    # 核心断言：AI 凭证密钥依然保留
    assert updated.ai_secret_encryption_key == fake_key
    assert get_settings().ai_secret_encryption_key == fake_key


@pytest.mark.asyncio
async def test_object_storage_dual_read_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """测试当前驱动为 S3 时，若远程未命中（404）能够平滑回退读取本地历史文件。"""
    from app.services.object_storage_service import ObjectStorageService

    # 构造本地历史文件
    local_root = tmp_path / "storage"
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(local_root))
    get_settings.cache_clear()

    test_key = "resources/workspace_1/legacy_image.png"
    target_file = local_root / test_key
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"legacy-file-content")

    # 切换为 S3 驱动
    apply_system_settings_override({
        "asset_storage_driver": "s3",
        "s3_bucket": "test-bucket",
        "s3_access_key": "AKTEST",
        "s3_secret_key": "SKTEST",
    })
    service = ObjectStorageService()
    assert service.driver == "s3"

    # 模拟 S3 _read_s3_object 报 404
    async def mock_s3_read(key: str, bucket_name: str | None = None):
        raise AppException(status_code=404, code="OBJECT_NOT_FOUND", detail="S3 不存在")

    monkeypatch.setattr(service, "_read_s3_object", mock_s3_read)

    # 核心验证：read_object 自动回退命中本地文件
    content = await service.read_object(test_key)
    assert content == b"legacy-file-content"

    # 核心验证：open_object_for_read 也回退打开本地文件
    async def mock_ensure_s3_cache(key: str, **kwargs):
        raise AppException(status_code=404, code="OBJECT_NOT_FOUND", detail="S3 不存在")

    monkeypatch.setattr(service, "_ensure_s3_cache_file", mock_ensure_s3_cache)
    async with service.open_object_for_read(test_key) as read_path:
        assert read_path == target_file
        assert read_path.read_bytes() == b"legacy-file-content"

@pytest.mark.asyncio
async def test_cross_process_version_sync():
    """测试跨进程版本同步：更新设置递增 Redis 版本号，且同步协程自动拉取 DB 更新配置。"""
    from app.core.config import get_local_settings_version, set_local_settings_version
    from app.models.system_setting import SystemSetting
    from app.services.redis_runtime_client import get_redis_runtime_client
    from app.services.system_settings_service import run_system_settings_version_sync_loop

    runtime = get_redis_runtime_client()
    ver_key = runtime.key("system_settings:version")
    init_ver = int(runtime.get(ver_key) or 0)

    # 1. 模拟一个实例保存设置
    ver_setting = SystemSetting(
        key="_settings_version",
        value=str(init_ver),
        category="system",
        description="系统配置持久化版本号",
        is_secret=False,
    )
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [ver_setting]
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_res.scalar.return_value = 0
    mock_session.execute.return_value = mock_res
    service = SystemSettingsService(mock_session)

    await service.update_settings({"session_ttl_hours": 96})
    new_ver = int(runtime.get(ver_key) or 0)
    assert new_ver > init_ver
    assert get_local_settings_version() == new_ver

    # 2. 模拟另一个实例（本地版本号落后为 init_ver）
    set_local_settings_version(init_ver)
    assert get_local_settings_version() == init_ver

    loaded = False
    async def mock_load(session):
        nonlocal loaded
        loaded = True
        return True, new_ver

    # 启动同步循环跑一小轮
    import asyncio
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.system_settings_service.load_system_settings_on_startup", mock_load)
        loop_task = asyncio.create_task(run_system_settings_version_sync_loop(MagicMock()))
        await asyncio.sleep(0.1)
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert loaded is True
    assert get_local_settings_version() == new_ver


@pytest.mark.asyncio
async def test_storage_migration_guard_blocks_s3_to_local_when_assets_exist():
    """测试当前使用 S3 且存在存量资源时，禁止直接切回本地存储（防止旧对象丢失）。"""
    apply_system_settings_override({
        "asset_storage_driver": "s3",
        "s3_bucket": "my-bucket",
        "s3_access_key": "AK123",
        "s3_secret_key": "SK456",
    })
    assert get_settings().asset_storage_driver == "s3"

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar.return_value = 5  # 模拟存在 5 个存量资源
    mock_session.execute.return_value = mock_res
    service = SystemSettingsService(mock_session)

    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"asset_storage_driver": "local"})
    assert exc_info.value.code == "STORAGE_MIGRATION_REQUIRED"


@pytest.mark.asyncio
async def test_storage_migration_guard_blocks_bucket_change_when_assets_exist():
    """测试当前存储桶有存量资源时，禁止直接更换新存储桶（防止跨桶对象丢失）。"""
    apply_system_settings_override({
        "asset_storage_driver": "s3",
        "s3_bucket": "old-bucket",
        "s3_access_key": "AK123",
        "s3_secret_key": "SK456",
    })

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar.return_value = 3  # 模拟存在 3 个存量资源
    mock_session.execute.return_value = mock_res
    service = SystemSettingsService(mock_session)

    with pytest.raises(AppException) as exc_info:
        await service.update_settings({"s3_bucket": "new-bucket"})
    assert exc_info.value.code == "BUCKET_MIGRATION_REQUIRED"


@pytest.mark.asyncio
async def test_storage_migration_guard_allows_change_when_no_assets():
    """测试当前无存量资源（count == 0）时，允许切回 local 或更换存储桶。"""
    apply_system_settings_override({
        "asset_storage_driver": "s3",
        "s3_bucket": "old-bucket",
        "s3_access_key": "AK123",
        "s3_secret_key": "SK456",
    })

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars
    mock_res.scalar.return_value = 0  # 无存量资源
    mock_session.execute.return_value = mock_res
    service = SystemSettingsService(mock_session)

    # 切回 local 允许通过
    res = await service.update_settings({"asset_storage_driver": "local"})
    assert res is not None


@pytest.mark.asyncio
async def test_storage_migration_guard_blocks_local_to_s3_when_assets_exist():
    """测试当前使用 local 且存在存量资源时，禁止直接切换到 S3 存储（防止未迁移导致公开访问 404）。"""
    apply_system_settings_override({
        "asset_storage_driver": "local",
    })
    assert get_settings().asset_storage_driver == "local"

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar.return_value = 8  # 模拟存在 8 个存量资源
    mock_session.execute.return_value = mock_res
    service = SystemSettingsService(mock_session)

    with pytest.raises(AppException) as exc_info:
        await service.update_settings({
            "asset_storage_driver": "s3",
            "s3_bucket": "target-bucket",
            "s3_access_key": "AK123",
            "s3_secret_key": "SK456",
        })
    assert exc_info.value.code == "STORAGE_MIGRATION_REQUIRED"


@pytest.mark.asyncio
async def test_load_system_settings_safe_on_db_failure(caplog: pytest.LogCaptureFixture):
    """测试 load_system_settings_on_startup 遭遇 DB 故障时不确认版本，返回 (False, 0) 并记录 WARNING。"""
    from app.services.system_settings_service import load_system_settings_on_startup

    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("DB connection refused")

    with caplog.at_level(logging.WARNING):
        ok, ver = await load_system_settings_on_startup(mock_session)

    assert ok is False
    assert ver == 0
    assert any("应用启动加载系统设置失败" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_version_sync_loop_recovers_on_redis_reset():
    """测试 Redis 版本重置或清空后（如 7 -> 1），非单调比对依然能触发全量对账与重载。"""
    from app.core.config import get_local_settings_version, set_local_settings_version
    from app.services.redis_runtime_client import get_redis_runtime_client
    from app.services.system_settings_service import run_system_settings_version_sync_loop

    runtime = get_redis_runtime_client()
    ver_key = runtime.key("system_settings:version")
    # 模拟本地持有一个较大版本 7
    set_local_settings_version(7)
    # 模拟 Redis 发生 FLUSHALL 或回滚到旧版本 1
    runtime.set(ver_key, "1")

    reloaded = False
    async def mock_load(session):
        nonlocal reloaded
        reloaded = True
        return True, 1

    import asyncio
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.system_settings_service.load_system_settings_on_startup", mock_load)
        loop_task = asyncio.create_task(run_system_settings_version_sync_loop(MagicMock()))
        await asyncio.sleep(0.1)
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert reloaded is True
    assert get_local_settings_version() == 1
