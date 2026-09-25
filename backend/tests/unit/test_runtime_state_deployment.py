"""文件功能：验证运行态 URL 严格解析、部署组合校验与同例隔离，避免误伤迁移脚本。"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.config import get_settings
from app.main import create_app
from app.services.redis_runtime_client import (
    RuntimeStateConfigurationError,
    create_runtime_state_client,
    parse_runtime_state_url,
    resolve_runtime_state_profile,
    validate_runtime_state_deployment,
)


@dataclass
class _DeploymentSettings:
    """仅用于部署组合校验的最小配置视图。"""

    database_url: str
    redis_url: str


def test_memory_url_should_require_explicit_instance_name() -> None:
    """`memory://` 必须带实例标识，且标识只是本进程配置名。"""

    assert parse_runtime_state_url("memory://lite") == ("memory", "lite")
    assert parse_runtime_state_url("  memory://lite  ") == ("memory", "lite")

    for invalid in ("memory://", "memory:///", "memory://lite/extra"):
        with pytest.raises(RuntimeStateConfigurationError):
            parse_runtime_state_url(invalid)


def test_unsupported_scheme_should_be_rejected() -> None:
    """不支持的 URL scheme 必须在启动校验阶段被拒绝。"""

    for invalid in ("", "   ", "http://127.0.0.1:6379", "unix:///tmp/redis.sock"):
        with pytest.raises(RuntimeStateConfigurationError):
            parse_runtime_state_url(invalid)

    assert parse_runtime_state_url("redis://127.0.0.1:6379/1") == ("redis", "")
    assert parse_runtime_state_url("rediss://cache.internal:6380/2") == ("rediss", "")


def test_runtime_state_profile_should_be_static_metadata() -> None:
    """就绪元数据只按 URL 静态判定后端类型与临时性，不建立连接。"""

    assert resolve_runtime_state_profile("memory://lite") == ("memory", True)
    assert resolve_runtime_state_profile("redis://127.0.0.1:6379/0") == ("redis", False)
    assert resolve_runtime_state_profile("rediss://cache.internal:6380/2") == ("redis", False)
    assert resolve_runtime_state_profile("http://invalid") == ("invalid", False)


def test_memory_runtime_should_reject_postgresql_combination() -> None:
    """memory:// 只适用于 SQLite Lite，与 PostgreSQL 组合必须启动失败。"""

    validate_runtime_state_deployment(
        _DeploymentSettings(
            database_url="sqlite+aiosqlite:////app/backend/data/web_presentation.db",
            redis_url="memory://lite",
        )
    )

    with pytest.raises(RuntimeStateConfigurationError):
        validate_runtime_state_deployment(
            _DeploymentSettings(
                database_url="postgresql+asyncpg://postgres:postgres@db:5432/web_presentation",
                redis_url="memory://lite",
            )
        )


def test_memory_runtime_should_reject_explicit_multi_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """进程内运行态不允许显式多 worker，真实 Redis 组合不受该限制。"""

    settings = _DeploymentSettings(
        database_url="sqlite+aiosqlite:////app/backend/data/web_presentation.db",
        redis_url="memory://lite",
    )
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeStateConfigurationError):
        validate_runtime_state_deployment(settings)

    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    validate_runtime_state_deployment(settings)

    validate_runtime_state_deployment(
        _DeploymentSettings(
            database_url="postgresql+asyncpg://postgres:postgres@db:5432/web_presentation",
            redis_url="redis://cache:6379/1",
        )
    )


def test_create_client_should_isolate_instances_and_prefixes() -> None:
    """`memory://test` 每例独立实例，前缀隔离不能互相污染。"""

    first = create_runtime_state_client(redis_url="memory://test", key_prefix="test_a")
    second = create_runtime_state_client(redis_url="memory://test", key_prefix="test_b")

    assert first.set(first.key("shared"), "first") is True
    assert second.get(second.key("shared")) is None
    assert first.backend_kind == "memory"
    assert first.ephemeral is True


def test_lifecycle_validation_should_not_break_migration_scripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """迁移脚本只为不连 Redis 而设置 memory:// 时，导入与建应用都不应被生命周期校验拦住。"""

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/web_presentation")
    monkeypatch.setenv("REDIS_URL", "memory://lite")
    get_settings.cache_clear()
    try:
        create_app()
        with pytest.raises(RuntimeStateConfigurationError):
            validate_runtime_state_deployment()
    finally:
        get_settings.cache_clear()