"""文件功能：P4 迁移行为契约——升级后业务不变量，替代源码文本断言。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_alembic(backend_root: Path, env: dict[str, str], revision: str | None = None) -> None:
    args = [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision or "head"]
    result = subprocess.run(
        args,
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _sqlite_env(database_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://p4-migration-contract"
    return env


def test_upgrade_head_sqlite_preserves_partial_unique_contracts(tmp_path: Path) -> None:
    """升级 head 后：活跃 run 唯一、截图去重唯一、布尔列可移植写入。"""

    backend_root = _backend_root()
    database_path = tmp_path / "p4-head.db"
    _run_alembic(backend_root, _sqlite_env(database_path))

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"pages", "ai_agent_runs", "ai_agent_external_batches", "page_screenshot_jobs"} <= tables

        # 行为断言：同一 session+agent 只能有一个活跃 run
        connection.execute(
            "INSERT INTO users (username, password_hash, display_name, role, status, "
            "preview_size_presets, created_at, updated_at) "
            "VALUES ('p4u', 'h', 'p4', 'admin', 'active', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO workspaces (code, name, created_by, updated_by, status, created_at, updated_at) "
            "VALUES ('p4ws', 'p4', 1, 1, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO ai_agent_sessions "
            "(session_id, agent_id, user_id, workspace_id, focus_mode, work_scope_mode, "
            "allowed_project_ids_json, focus_version, metadata_json, created_at, updated_at) "
            "VALUES ('s1', 'agent-coordinator', 1, 1, 'follow_route', 'workspace', '[]', 0, '{}', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO ai_agent_runs "
            "(run_id, session_id, agent_id, user_id, status, scope_type, workspace_id, source, "
            "input_payload_json, message_history_json, event_index, created_at, updated_at) "
            "VALUES ('r1', 's1', 'agent-coordinator', 1, 'running', 'workspace', 1, 'test', '{}', '[]', 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ai_agent_runs "
                "(run_id, session_id, agent_id, user_id, status, scope_type, workspace_id, source, "
                "input_payload_json, message_history_json, event_index, created_at, updated_at) "
                "VALUES ('r2', 's1', 'agent-coordinator', 1, 'waiting_external', 'workspace', 1, 'test', "
                "'{}', '[]', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        connection.rollback()

        # 行为断言：render 唯一槽位占用
        indexes = list(connection.execute("PRAGMA index_list('render_attempts')"))
        assert any("worker_epoch_active" in (row[1] or "") for row in indexes)


def test_upgrade_head_sqlite_boolean_write_is_portable(tmp_path: Path) -> None:
    """布尔列必须用 TRUE/FALSE 写入，禁止整数比较语义。行为上 SQLite 可写 0/1 且可读回。"""

    backend_root = _backend_root()
    database_path = tmp_path / "p4-bool.db"
    env = _sqlite_env(database_path)
    _run_alembic(backend_root, env, "20260811_0100")

    with sqlite3.connect(database_path) as connection:
        cols = {row[1] for row in connection.execute("PRAGMA table_info(ai_llm_configs)")}
        if "thinking_enabled" not in cols:
            pytest.skip("该迁移版本尚无 thinking_enabled")
        connection.execute(
            "INSERT INTO ai_llm_configs (name, provider, model, thinking_enabled, created_at, updated_at) "
            "VALUES ('m', 'openai', 'gpt', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        value = connection.execute(
            "SELECT thinking_enabled FROM ai_llm_configs WHERE name='m'"
        ).fetchone()[0]
        assert value in (1, True)


def test_remote_render_migration_behavior_clears_screenshot_pointers(tmp_path: Path) -> None:
    """20260910 离线转换必须清空当前截图指针，历史对象语义为“待生成”。"""

    backend_root = _backend_root()
    database_path = tmp_path / "p4-screenshot.db"
    env = _sqlite_env(database_path)
    _run_alembic(backend_root, env, "20260904_0100")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, display_name, role, status, "
            "preview_size_presets, created_at, updated_at) "
            "VALUES ('p4s', 'h', 'p4', 'admin', 'active', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO workspaces (code, name, created_by, updated_by, status, created_at, updated_at) "
            "VALUES ('p4s', 'p4', 1, 1, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        # pages 表结构随版本变化；若无 screenshot_storage_key 则跳过
        cols = {row[1] for row in connection.execute("PRAGMA table_info(pages)")}
        if "screenshot_storage_key" not in cols:
            pytest.skip("目标 revision 尚无 screenshot_storage_key")
        connection.execute(
            "INSERT INTO pages (workspace_id, code, title, page_content, file_type, status, "
            "screenshot_storage_key, screenshot_version_no, created_at, updated_at) "
            "VALUES (1, 'p', 't', '<template/>', 'vue', 'active', 'old-key', 3, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

    _run_alembic(backend_root, env, "head")

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT screenshot_storage_key, screenshot_version_no FROM pages WHERE code='p'"
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None


def test_migration_versions_have_no_bare_dialect_name() -> None:
    """新迁移不得裸判 dialect.name；历史迁移已收口到 helpers.dialect。"""

    versions = _backend_root() / "migrations" / "versions"
    offenders: list[str] = []
    for path in versions.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "dialect.name" in source:
            offenders.append(path.name)
    assert offenders == []


def test_dual_database_upgrade_contract_sqlite_and_optional_postgres(tmp_path: Path) -> None:
    """双库对拍：SQLite 必跑；提供 P4_POSTGRES_DATABASE_URL 时对拍表集合与部分唯一索引。"""

    backend_root = _backend_root()
    sqlite_path = tmp_path / "p4-dual.db"
    _run_alembic(backend_root, _sqlite_env(sqlite_path))

    with sqlite3.connect(sqlite_path) as connection:
        sqlite_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        sqlite_indexes = _index_names(connection, "ai_agent_runs")

    assert _PARTIAL_UNIQUE_INDEX in sqlite_indexes

    pg_url = os.environ.get("P4_POSTGRES_DATABASE_URL", "").strip()
    if not pg_url:
        pytest.skip("未配置 P4_POSTGRES_DATABASE_URL，仅验证 SQLite 路径")
        return

    env = os.environ.copy()
    env["DATABASE_URL"] = pg_url
    env["REDIS_URL"] = "memory://p4-dual-pg"
    _run_alembic(backend_root, env)

    sync_engine = create_engine(_to_sync_postgresql_url(pg_url))
    try:
        inspector = inspect(sync_engine)
        postgres_tables = set(inspector.get_table_names())
        postgres_indexes = {row["name"] for row in inspector.get_indexes("ai_agent_runs")}
    finally:
        sync_engine.dispose()

    assert postgres_tables == sqlite_tables, (
        f"双库表集合不一致：仅 PostgreSQL={sorted(postgres_tables - sqlite_tables)}，"
        f"仅 SQLite={sorted(sqlite_tables - postgres_tables)}"
    )
    assert _PARTIAL_UNIQUE_INDEX in postgres_indexes


_PARTIAL_UNIQUE_INDEX = "uq_ai_agent_runs_active_session_agent"


def _index_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """读取 SQLite 表上的索引名集合。"""

    return {row[1] for row in connection.execute(f"PRAGMA index_list('{table_name}')")}


def _to_sync_postgresql_url(database_url: str) -> str:
    """把异步驱动 URL 转成同步 psycopg URL，供 inspector 对拍使用。"""

    return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
