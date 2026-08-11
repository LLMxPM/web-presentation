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


def test_content_agent_toolset_migration_should_reset_configs_and_preserve_messages(tmp_path: Path) -> None:
    """工具体系迁移应取消旧活动运行、清空内容助手覆盖，但保留会话历史。"""

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
        assert connection.execute("SELECT status, error_code FROM ai_agent_runs WHERE run_id = 'run-old'").fetchone() == ("cancelled", "AI_TOOLSET_MIGRATED")
        assert connection.execute("SELECT status FROM ai_agent_requirements WHERE requirement_id = 'req-old'").fetchone() == ("cancelled",)
        assert connection.execute("SELECT status FROM ai_agent_tool_calls WHERE tool_call_id = 'call-old'").fetchone() == ("error",)
        assert connection.execute("SELECT content FROM ai_agent_messages WHERE run_id = 'run-old'").fetchone() == ("需要保留的历史消息",)
        session_row = connection.execute(
            "SELECT focus_mode, pinned_project_id, work_scope_mode, allowed_project_ids_json, focus_version, deleted_at FROM ai_agent_sessions WHERE session_id = 'session-old'"
        ).fetchone()
        assert session_row is not None
        assert session_row[:5] == ("follow_route", None, "workspace", "[]", 0)
        assert session_row[5] is not None
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_agent_sessions)").fetchall()}
        assert {"scope_type", "project_id", "page_id", "component_id", "source"}.isdisjoint(columns)


def test_llm_reasoning_capability_migration_should_normalize_legacy_values(tmp_path: Path) -> None:
    """模型能力迁移应规范化旧档位，并能完整降级回旧表结构。"""

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
        rows = connection.execute(
            "SELECT id, reasoning_mode, reasoning_level, context_window_tokens FROM ai_llm_configs ORDER BY id"
        ).fetchall()
        assert rows == [
            (1, "auto", None, 128000),
            (2, "enabled", "low", 128000),
            (3, "enabled", "low", 128000),
            (4, "enabled", "max", 128000),
            (5, "disabled", None, 128000),
            (6, "enabled", "high", 128000),
            (7, "enabled", "medium", 128000),
        ]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_llm_configs)").fetchall()}
        assert {"thinking_enabled", "thinking_effort", "max_output_tokens"}.isdisjoint(columns)
        assert {"model_max_output_tokens", "request_max_output_tokens", "compression_target_ratio"}.isdisjoint(columns)
        assert {"reasoning_mode", "reasoning_level", "model_capability_json"}.issubset(columns)

    _run_alembic(backend_root, env, "20260809_0100", command="downgrade")

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(ai_llm_configs)").fetchall()}
        assert {"thinking_enabled", "thinking_effort", "max_output_tokens"}.issubset(columns)
        assert {"reasoning_mode", "reasoning_level", "model_capability_json"}.isdisjoint(columns)
        assert connection.execute(
            "SELECT thinking_enabled, thinking_effort, max_output_tokens FROM ai_llm_configs WHERE id = 4"
        ).fetchone() == (1, "max", 32768)


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
