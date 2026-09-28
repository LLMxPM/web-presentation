"""文件功能：验证部署 profile 派生，以及 SQLite Lite 与多进程/多副本组合的启动拒绝。"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.db.sqlite_single_process as guard_module
from app.core.config import AppSettings, get_settings
from app.db.profile import resolve_deployment_profile
from app.db.sqlite_single_process import (
    SqliteSingleProcessViolation,
    ensure_sqlite_single_process,
)

POSTGRES_URL = "postgresql+asyncpg://postgres:postgres@db:5432/web_presentation"
SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _settings(**overrides: object) -> AppSettings:
    """构造不读取仓库 .env 的最小测试配置。"""

    base: dict[str, object] = {
        "_env_file": None,
        "database_url": POSTGRES_URL,
        "redis_url": "redis://127.0.0.1:6379/0",
        "backend_multi_instance": False,
    }
    base.update(overrides)
    return AppSettings(**base)  # type: ignore[arg-type]


def _file_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


@pytest.fixture(autouse=True)
def _clean_process_topology(monkeypatch: pytest.MonkeyPatch):
    """进程拓扑来自环境变量、守卫是模块级全局；每个用例都从干净状态开始。"""

    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    previous = guard_module._process_guard
    guard_module._process_guard = None
    yield
    current = guard_module._process_guard
    if current is not None:
        current.release()
    guard_module._process_guard = previous


def test_sqlite_file_profile_is_lite() -> None:
    """SQLite 文件库 = Lite：单写库，不允许多 Backend 进程。"""

    profile = resolve_deployment_profile(
        _settings(database_url="sqlite+aiosqlite:////app/backend/data/web_presentation.db")
    )

    assert profile.is_lite is True
    assert profile.is_distributed is False
    assert profile.name == "sqlite-lite"
    assert profile.backend_multi_process_allowed is False
    assert profile.multi_process_requested is False


def test_sqlite_memory_profile_is_also_lite() -> None:
    """内存库同属 Lite：进程私有单写库，不因没有文件而放宽拓扑约束。"""

    profile = resolve_deployment_profile(_settings(database_url=SQLITE_MEMORY_URL))

    assert profile.is_lite is True
    assert profile.backend_multi_process_allowed is False


def test_postgres_profile_is_distributed() -> None:
    """PostgreSQL = 分布式形态，多 Backend 进程合法。"""

    profile = resolve_deployment_profile(_settings())

    assert profile.is_distributed is True
    assert profile.is_lite is False
    assert profile.name == "postgresql-distributed"
    assert profile.backend_multi_process_allowed is True


def test_postgres_with_replica_declaration_is_legal(monkeypatch: pytest.MonkeyPatch) -> None:
    """PostgreSQL + 副本声明 / 多 worker 都是合法的多进程组合。"""

    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    profile = resolve_deployment_profile(_settings(backend_multi_instance=True))

    assert profile.declared_multi_instance is True
    assert profile.explicit_worker_count == ("WEB_CONCURRENCY", 4)
    assert profile.multi_process_requested is True
    assert profile.backend_multi_process_allowed is True
    # 守卫只对 SQLite 生效：PostgreSQL 直接放行，不取文件锁。
    assert ensure_sqlite_single_process(POSTGRES_URL) is None


def test_worker_env_alone_marks_multi_process_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """只声明 worker 数、不声明副本，也构成多进程请求。"""

    monkeypatch.setenv("UVICORN_WORKERS", "3")
    profile = resolve_deployment_profile(_settings())

    assert profile.declared_multi_instance is False
    assert profile.explicit_worker_count == ("UVICORN_WORKERS", 3)
    assert profile.multi_process_requested is True


def test_single_worker_env_is_not_multi_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 数显式为 1 不算多进程声明，Lite 仍可启动。"""

    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    assert resolve_deployment_profile(_settings()).multi_process_requested is False


def test_sqlite_file_rejects_multi_worker_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """既有边界不变：SQLite 文件库 + WEB_CONCURRENCY>1 启动失败，消息仍指向 worker 数。"""

    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(SqliteSingleProcessViolation) as excinfo:
        ensure_sqlite_single_process(_file_url(tmp_path / "lite.db"))

    assert "WEB_CONCURRENCY=2" in str(excinfo.value)


def test_sqlite_file_rejects_backend_multi_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """新增边界：compose 扩副本但每容器仍是单 worker，也必须拒绝 SQLite 文件库。"""

    monkeypatch.setattr(get_settings(), "backend_multi_instance", True)
    with pytest.raises(SqliteSingleProcessViolation) as excinfo:
        ensure_sqlite_single_process(_file_url(tmp_path / "lite.db"))

    assert "BACKEND_MULTI_INSTANCE=true" in str(excinfo.value)


def test_sqlite_file_acquires_guard_under_single_process(tmp_path: Path) -> None:
    """合法 Lite 组合仍正常取到单进程锁，新增校验不得误伤单机部署。"""

    guard = ensure_sqlite_single_process(_file_url(tmp_path / "lite.db"))

    assert guard is not None
    assert guard_module._process_guard is guard
