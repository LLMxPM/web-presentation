"""文件功能：验证 Alembic 完整迁移可在 SQLite 轻量部署数据库上执行。"""

from __future__ import annotations

import os
import runpy
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_ai_attachment_lifecycle_foreign_key_names_fit_postgresql_limit() -> None:
    """显式外键名不得超过 PostgreSQL 的 63 字节标识符上限。"""

    backend_root = Path(__file__).resolve().parents[2]
    migration_path = backend_root / "migrations" / "versions" / "20260809_0100_ai_attachment_asset_lifecycle.py"
    migration_globals = runpy.run_path(str(migration_path))

    foreign_key_names = migration_globals["_FK_NAMES"].values()
    assert all(len(name.encode("utf-8")) <= 63 for name in foreign_key_names)


def test_llm_reasoning_migration_should_use_portable_boolean_sql() -> None:
    """推理能力迁移不得用整数比较或写入布尔列，确保 PostgreSQL 与 SQLite 均可执行。"""

    backend_root = Path(__file__).resolve().parents[2]
    migration_path = backend_root / "migrations" / "versions" / "20260811_0100_llm_reasoning_capabilities.py"
    source = migration_path.read_text(encoding="utf-8")

    assert "thinking_enabled = 0" not in source
    assert "thinking_enabled IS FALSE" in source
    assert "THEN TRUE ELSE FALSE" in source


def test_alembic_head_should_migrate_sqlite_database(tmp_path: Path) -> None:
    """SQLite 模式应能从空库迁移到当前 head，保障轻量部署首次启动可用。"""

    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "web_presentation.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://sqlite-migration-test"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert database_path.exists()


def test_remove_self_delegation_migration_should_purge_history_and_restore_empty_schema(tmp_path: Path) -> None:
    """升级应清空 AI 历史并保留配置与业务数据，降级只恢复空 Member 结构。"""

    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "remove-self-delegation.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://remove-self-delegation-test"
    _run_alembic(backend_root, env, "20260817_0100")

    with sqlite3.connect(database_path) as connection:
        project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()
        connection.execute(
            "INSERT INTO ai_agent_user_configs "
            "(user_id, agent_id, description_override, prompt_override, prompt_mode) "
            "VALUES (1, 'agent-coordinator', '保留描述', '保留提示词', 'override')"
        )
        connection.executemany(
            "INSERT INTO ai_agent_tool_user_configs "
            "(user_id, agent_id, tool_key, enabled, instructions_override) VALUES (1, 'agent-coordinator', ?, 1, ?)",
            [("delegate_task_to_self", "删除此配置"), ("list_entities", "保留此配置")],
        )
        connection.execute(
            "INSERT INTO ai_agent_sessions "
            "(session_id, agent_id, user_id, workspace_id, focus_mode, work_scope_mode, "
            "allowed_project_ids_json, focus_version, metadata_json) "
            "VALUES ('session-remove-self', 'agent-coordinator', 1, 1, 'follow_route', 'workspace', '[]', 0, '{}')"
        )
        connection.execute(
            "INSERT INTO ai_agent_runs "
            "(run_id, session_id, agent_id, user_id, status, scope_type, workspace_id, source, "
            "input_payload_json, message_history_json, event_index) "
            "VALUES ('run-remove-self', 'session-remove-self', 'agent-coordinator', 1, 'paused', "
            "'workspace', 1, 'test', '{}', '[]', 0)"
        )
        connection.execute(
            "INSERT INTO ai_agent_member_runs "
            "(member_run_id, parent_run_id, session_id, agent_id, status, input_payload_json, message_history_json) "
            "VALUES ('member-remove-self', 'run-remove-self', 'session-remove-self', 'agent-coordinator', "
            "'running', '{}', '[]')"
        )
        connection.execute(
            "INSERT INTO ai_agent_messages (session_id, run_id, role, content, attachments_json, order_index) "
            "VALUES ('session-remove-self', 'run-remove-self', 'assistant', '历史消息', '[]', 0)"
        )
        connection.execute(
            "INSERT INTO ai_agent_run_events (session_id, run_id, event_index, event, payload_json) "
            "VALUES ('session-remove-self', 'run-remove-self', 0, 'run.started', '{}')"
        )
        connection.execute(
            "INSERT INTO ai_agent_tool_calls "
            "(session_id, run_id, member_run_id, tool_call_id, tool_name, status) "
            "VALUES ('session-remove-self', 'run-remove-self', 'member-remove-self', 'call-old', "
            "'delegate_task_to_self', 'running')"
        )
        connection.execute(
            "INSERT INTO ai_agent_requirements "
            "(requirement_id, session_id, run_id, kind, status, tool_call_id, tool_name, "
            "member_agent_id, member_agent_name, member_run_id, payload_json) "
            "VALUES ('req-old', 'session-remove-self', 'run-remove-self', 'confirmation', 'pending', "
            "'call-old', 'delegate_task_to_self', 'agent-coordinator', '内容助手', 'member-remove-self', '{}')"
        )
        connection.execute(
            "INSERT INTO ai_agent_image_attachments "
            "(user_id, workspace_id, session_id, run_id, source_kind, storage_key, original_name, "
            "content_type, file_size, sha256, owned_object, status) "
            "VALUES (1, 1, 'session-remove-self', 'run-remove-self', 'user_upload', 'orphan/key.png', "
            "'key.png', 'image/png', 10, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 1, 'active')"
        )
        connection.commit()

    _run_alembic(backend_root, env, "head")

    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "ai_agent_member_runs" not in tables
        for table in (
            "ai_agent_sessions",
            "ai_agent_runs",
            "ai_agent_messages",
            "ai_agent_run_events",
            "ai_agent_tool_calls",
            "ai_agent_requirements",
            "ai_agent_image_attachments",
            "ai_agent_external_batches",
            "ai_agent_external_tasks",
            "ai_page_mutation_batches",
            "ai_page_mutation_jobs",
            "ai_image_generation_jobs",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM ai_agent_user_configs").fetchone() == (1,)
        assert connection.execute(
            "SELECT tool_key FROM ai_agent_tool_user_configs ORDER BY tool_key"
        ).fetchall() == [("list_entities",)]
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone() == project_count
        for table in (
            "ai_agent_tool_calls",
            "ai_agent_requirements",
            "ai_agent_external_batches",
            "ai_agent_external_tasks",
            "ai_page_mutation_jobs",
            "ai_image_generation_jobs",
        ):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert "member_run_id" not in columns

    _run_alembic(backend_root, env, "20260817_0100", command="downgrade")

    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "ai_agent_member_runs" in tables
        assert connection.execute("SELECT COUNT(*) FROM ai_agent_member_runs").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM ai_agent_sessions").fetchone() == (0,)
        for table in (
            "ai_agent_tool_calls",
            "ai_agent_requirements",
            "ai_agent_external_batches",
            "ai_agent_external_tasks",
            "ai_page_mutation_jobs",
            "ai_image_generation_jobs",
        ):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            assert "member_run_id" in columns


def test_remove_self_delegation_migration_should_keep_postgresql_partial_index_contract() -> None:
    """PostgreSQL 必须原地删列，并保留新旧 collecting 部分索引谓词。"""

    backend_root = Path(__file__).resolve().parents[2]
    source = (
        backend_root / "migrations" / "versions" / "20260818_0100_remove_self_delegation.py"
    ).read_text(encoding="utf-8")

    assert 'postgresql_where=sa.text("status = \'collecting\'")' in source
    assert "postgresql_where=sa.text(\"status = 'collecting' AND member_run_id IS NULL\")" in source
    assert "postgresql_where=sa.text(\"status = 'collecting' AND member_run_id IS NOT NULL\")" in source
    assert 'if op.get_bind().dialect.name == "sqlite":' in source
    assert "inspector = sa.inspect(op.get_bind())" in source
    assert "op.drop_column(table_name, column_name)" in source


def test_content_agent_toolset_migration_should_reset_configs_and_runtime_history(tmp_path: Path) -> None:
    """最终模型拆分迁移应清空旧 AI 配置及运行历史。"""

    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "content-agent-migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://content-agent-migration-test"
    _run_alembic(backend_root, env, "20260730_0100")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO ai_agent_user_configs (user_id, agent_id, description_override, prompt_override, prompt_mode) VALUES (1, 'agent-coordinator', '旧描述', '旧提示词', 'override')"
        )
        connection.execute(
            "INSERT INTO ai_agent_tool_user_configs (user_id, agent_id, tool_key, enabled, instructions_override) VALUES (1, 'agent-coordinator', 'create_project_page', 1, '旧工具提示词')"
        )
        connection.execute(
            "INSERT INTO ai_agent_user_configs (user_id, agent_id, description_override, prompt_override, prompt_mode) VALUES (1, 'component-manager', '旧组件描述', '旧组件提示词', 'override')"
        )
        connection.execute(
            "INSERT INTO ai_agent_user_configs (user_id, agent_id, description_override, prompt_override, prompt_mode) VALUES (1, 'resource-manager', '旧资源描述', '旧资源提示词', 'override')"
        )
        connection.execute(
            "INSERT INTO ai_agent_sessions (session_id, agent_id, user_id, session_name, scope_type, workspace_id, source, metadata_json) VALUES ('session-old', 'agent-coordinator', 1, '旧会话', 'workspace', 1, 'test', '{}')"
        )
        connection.execute(
            "INSERT INTO ai_agent_runs (run_id, session_id, agent_id, user_id, status, scope_type, workspace_id, source, input_payload_json, message_history_json, pending_requirement_json, event_index) VALUES ('run-old', 'session-old', 'agent-coordinator', 1, 'paused', 'workspace', 1, 'test', '{}', '[]', '{}', 0)"
        )
        connection.execute(
            "INSERT INTO ai_agent_messages (session_id, run_id, role, content, attachments_json, order_index) VALUES ('session-old', 'run-old', 'assistant', '需要保留的历史消息', '[]', 0)"
        )
        connection.execute(
            "INSERT INTO ai_agent_tool_calls (session_id, run_id, tool_call_id, tool_name, status) VALUES ('session-old', 'run-old', 'call-old', 'create_project_page', 'running')"
        )
        connection.execute(
            "INSERT INTO ai_agent_requirements (requirement_id, session_id, run_id, kind, status, tool_call_id, tool_name, payload_json) VALUES ('req-old', 'session-old', 'run-old', 'confirmation', 'pending', 'call-old', 'create_project_page', '{}')"
        )
        connection.commit()

    _run_alembic(backend_root, env, "head")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ai_agent_user_configs WHERE agent_id = 'agent-coordinator'").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM ai_agent_tool_user_configs WHERE agent_id = 'agent-coordinator'").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM ai_agent_user_configs WHERE agent_id IN ('component-manager', 'resource-manager')").fetchone() == (0,)
        for table in ("ai_agent_runs", "ai_agent_requirements", "ai_agent_tool_calls", "ai_agent_messages", "ai_agent_sessions"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_agent_sessions)").fetchall()}
        assert {"scope_type", "project_id", "page_id", "component_id", "source"}.isdisjoint(columns)


def test_model_split_migration_should_reset_legacy_values_and_restore_empty_tables_on_downgrade(tmp_path: Path) -> None:
    """模型拆分不迁移旧值，降级也只恢复空的旧表结构。"""

    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "llm-reasoning-migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://llm-reasoning-migration-test"
    _run_alembic(backend_root, env, "20260809_0100")

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            "INSERT INTO ai_llm_provider_configs (id, scope, name, provider_key, status) VALUES (?, 'global', ?, ?, 'active')",
            [(1, "OpenAI 旧配置", "openai"), (2, "DeepSeek 旧配置", "deepseek")],
        )
        legacy_rows = [
            (1, "关闭旧开关", 1, 0, "high"),
            (2, "低档", 1, 1, "low"),
            (3, "Minimal", 1, 1, "minimal"),
            (4, "Ultra", 1, 1, "ultra"),
            (5, "显式关闭", 1, 1, "off"),
            (6, "供应商默认", 2, 1, "future-level"),
            (7, "平台默认", 1, 1, "future-level"),
        ]
        connection.executemany(
            """
            INSERT INTO ai_llm_configs (
                id, scope, name, provider_config_id, model_id, model_type,
                thinking_enabled, thinking_effort, supports_image_input,
                context_window_tokens, max_output_tokens, history_token_ratio,
                compression_target_ratio, advanced_config_json, status
            ) VALUES (?, 'global', ?, ?, 'legacy-model', 'chat', ?, ?, 0, 128000, 25600, 1.0, 0.1, '{}', 'active')
            """,
            legacy_rows,
        )
        connection.commit()

    _run_alembic(backend_root, env, "head")

    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        assert "ai_llm_configs" not in tables
        assert {"ai_chat_provider_configs", "ai_chat_model_configs", "ai_chat_slot_bindings"}.issubset(tables)
        assert {"ai_image_provider_configs", "ai_image_model_configs", "ai_image_slot_bindings"}.issubset(tables)
        assert connection.execute("SELECT COUNT(*) FROM ai_chat_model_configs").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM ai_image_model_configs").fetchone() == (0,)
        catalog_columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_chat_model_catalog)").fetchall()}
        model_columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_chat_model_configs)").fetchall()}
        assert "protocol_key" in catalog_columns
        assert "protocol_key" in model_columns

    _run_alembic(backend_root, env, "20260809_0100", command="downgrade")

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_llm_configs)").fetchall()}
        assert {"thinking_enabled", "thinking_effort", "max_output_tokens"}.issubset(columns)
        assert {"reasoning_mode", "reasoning_level", "model_capability_json"}.isdisjoint(columns)
        assert connection.execute("SELECT COUNT(*) FROM ai_llm_configs").fetchone() == (0,)


def test_pat_flexible_authorization_migration_preserves_old_tokens_and_downgrades_long_lived_tokens(tmp_path: Path) -> None:
    """PAT 迁移应保留旧令牌，并能将长期令牌安全降级为有限有效期。"""

    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "pat-flexible-authorization.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://pat-flexible-authorization-test"
    _run_alembic(backend_root, env, "20260823_0100")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO api_access_tokens "
            "(user_id, name, token_public_id, token_hash, expires_at) "
            "VALUES (999, '旧令牌', 'old-token-public', 'old-token-hash', '2027-01-01 00:00:00')"
        )
        connection.commit()

    _run_alembic(backend_root, env, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(api_access_tokens)")}
        assert columns["expires_at"][3] == 0
        assert connection.execute(
            "SELECT all_workspaces FROM api_access_tokens WHERE token_public_id = 'old-token-public'"
        ).fetchone() == (0,)
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO api_access_tokens "
            "(user_id, name, token_public_id, token_hash, expires_at, all_workspaces) "
            "VALUES (999, '长期令牌', 'long-token-public', 'long-token-hash', NULL, 1)"
        )
        connection.commit()

    _run_alembic(backend_root, env, "20260823_0100", command="downgrade")

    with sqlite3.connect(database_path) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(api_access_tokens)")}
        assert "all_workspaces" not in columns
        assert columns["expires_at"][3] == 1
        assert connection.execute(
            "SELECT expires_at IS NOT NULL FROM api_access_tokens WHERE token_public_id = 'long-token-public'"
        ).fetchone() == (1,)


def _run_alembic(backend_root: Path, env: dict[str, str], revision: str, *, command: str = "upgrade") -> None:
    """运行指定 Alembic 升降级，并在失败时输出完整诊断。"""

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", command, revision],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
