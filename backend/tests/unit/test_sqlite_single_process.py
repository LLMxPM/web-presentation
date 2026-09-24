"""文件功能：验证 SQLite 单进程边界守卫拒绝多 worker、幂等复用与换库重绑定语义。"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.db.sqlite_single_process as guard_module
from app.db.sqlite_single_process import (
    SqliteSingleProcessViolation,
    ensure_sqlite_single_process,
)


@pytest.fixture(autouse=True)
def _isolated_process_guard():
    """守卫是模块级全局；每个用例从干净状态开始并在结束时释放，避免污染 create_app 测试。"""

    previous = guard_module._process_guard
    guard_module._process_guard = None
    yield
    current = guard_module._process_guard
    if current is not None:
        current.release()
    guard_module._process_guard = previous


def _file_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def test_sqlite_memory_url_skips_guard() -> None:
    """内存库不启用单进程文件锁。"""

    assert ensure_sqlite_single_process("sqlite+aiosqlite:///:memory:") is None


def test_postgres_url_skips_guard() -> None:
    """非 SQLite 不启用该守卫。"""

    assert ensure_sqlite_single_process("postgresql+asyncpg://u:p@localhost/db") is None


def test_multi_worker_env_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """WEB_CONCURRENCY>1 与 SQLite 文件库互斥。"""

    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(SqliteSingleProcessViolation):
        ensure_sqlite_single_process(_file_url(tmp_path / "lite.db"))


def test_same_database_acquire_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一进程对同一库重复启动校验应复用已有锁，不误伤自身。"""

    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    url = _file_url(tmp_path / "lite-idem.db")

    first = ensure_sqlite_single_process(url)
    assert first is not None
    assert ensure_sqlite_single_process(url) is first


def test_different_database_rebinds_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """换库调用必须重新绑定到新库，否则后续库处于无守卫状态。"""

    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    first_db = tmp_path / "first.db"
    second_db = tmp_path / "second.db"

    first = ensure_sqlite_single_process(_file_url(first_db))
    second = ensure_sqlite_single_process(_file_url(second_db))

    assert first is not None
    assert second is not first
    assert second.database_path == second_db.resolve()
    assert guard_module._process_guard is second
    # 旧库的锁必须已释放：重新绑定回旧库应当成功而不是报冲突。
    rebound = ensure_sqlite_single_process(_file_url(first_db))
    assert rebound is not None
    assert rebound.database_path == first_db.resolve()
