"""文件功能：清空旧 AI 运行数据并将聊天模型、图片模型和 Models.dev 目录拆表。

Revision ID: 20260812_0100
Revises: 20260811_0200
Create Date: 2026-08-12 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_0100"
down_revision: Union[str, Sequence[str], None] = "20260811_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """按外键顺序重置 AI 数据并创建完全隔离的新模型域。"""

    for table in (
        "ai_image_generation_jobs",
        "ai_page_mutation_jobs",
        "ai_page_mutation_batches",
        "ai_agent_requirements",
        "ai_agent_tool_calls",
        "ai_agent_messages",
        "ai_agent_run_events",
        "ai_agent_member_runs",
        "ai_agent_runs",
        "ai_agent_sessions",
        "ai_agent_image_attachments",
        "ai_llm_slot_bindings",
        "ai_llm_configs",
        "ai_llm_provider_configs",
    ):
        op.execute(sa.text(f"DELETE FROM {table}"))

    op.drop_table("ai_image_generation_jobs")
    op.drop_table("ai_llm_slot_bindings")
    op.drop_table("ai_llm_configs")
    op.drop_table("ai_llm_provider_configs")

    _create_catalog_tables()
    _create_chat_tables()
    _create_image_tables()
    _create_image_job_table()


def downgrade() -> None:
    """删除新域并恢复空的旧混合模型表；历史数据不会恢复。"""

    op.drop_table("ai_image_generation_jobs")
    op.drop_table("ai_image_slot_bindings")
    op.drop_table("ai_image_model_configs")
    op.drop_table("ai_image_provider_configs")
    op.drop_table("ai_chat_slot_bindings")
    op.drop_table("ai_chat_model_configs")
    op.drop_table("ai_chat_provider_configs")
    op.drop_table("ai_chat_model_catalog")
    op.drop_table("ai_chat_provider_catalog")
    op.drop_table("ai_model_catalog_sync_state")
    _create_legacy_llm_tables()


def _timestamps() -> list[sa.Column]:
    """返回统一时间戳列。"""

    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _audit() -> list[sa.Column]:
    """返回统一审计列。"""

    return [sa.Column("created_by", sa.Integer(), nullable=True), sa.Column("updated_by", sa.Integer(), nullable=True)]


def _create_catalog_tables() -> None:
    """创建目录缓存及状态表。"""

    op.create_table(
        "ai_model_catalog_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("etag", sa.String(512), nullable=True),
        sa.Column("catalog_version", sa.String(64), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_model_catalog_sync_state_lease_expires_at", "ai_model_catalog_sync_state", ["lease_expires_at"])
    op.create_table(
        "ai_chat_provider_catalog",
        sa.Column("provider_key", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("api_url", sa.Text(), nullable=True),
        sa.Column("docs_url", sa.Text(), nullable=True),
        sa.Column("default_base_url", sa.Text(), nullable=True),
        sa.Column("npm_package", sa.String(255), nullable=True),
        sa.Column("env_keys_json", sa.JSON(), nullable=False),
        sa.Column("protocol_key", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
    )
    for column in ("name", "protocol_key", "is_current", "catalog_version"):
        op.create_index(f"ix_ai_chat_provider_catalog_{column}", "ai_chat_provider_catalog", [column])
    op.create_table(
        "ai_chat_model_catalog",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider_key", sa.String(128), sa.ForeignKey("ai_chat_provider_catalog.provider_key"), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("family", sa.String(128), nullable=True),
        sa.Column("status", sa.String(64), nullable=True),
        sa.Column("release_date", sa.String(32), nullable=True),
        sa.Column("last_updated", sa.String(32), nullable=True),
        sa.Column("context_tokens", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("input_modalities_json", sa.JSON(), nullable=False),
        sa.Column("output_modalities_json", sa.JSON(), nullable=False),
        sa.Column("supports_tool_call", sa.Boolean(), nullable=False),
        sa.Column("supports_structured_output", sa.Boolean(), nullable=False),
        sa.Column("supports_attachment", sa.Boolean(), nullable=False),
        sa.Column("supports_reasoning", sa.Boolean(), nullable=False),
        sa.Column("reasoning_options_json", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("provider_key", "model_id", name="uq_ai_chat_model_catalog_provider_model"),
    )
    for column in ("provider_key", "model_id", "name", "status", "is_current", "catalog_version"):
        op.create_index(f"ix_ai_chat_model_catalog_{column}", "ai_chat_model_catalog", [column])
    op.create_index("ix_ai_chat_model_catalog_lookup", "ai_chat_model_catalog", ["provider_key", "is_current", "name"])


def _create_chat_tables() -> None:
    """创建聊天供应商、模型和策略绑定表。"""

    op.create_table(
        "ai_chat_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("catalog_provider_key", sa.String(128), sa.ForeignKey("ai_chat_provider_catalog.provider_key"), nullable=True),
        sa.Column("protocol_key", sa.String(64), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        *_audit(), *_timestamps(),
    )
    for column in ("user_id", "scope", "provider_key", "catalog_provider_key", "protocol_key", "status"):
        op.create_index(f"ix_ai_chat_provider_configs_{column}", "ai_chat_provider_configs", [column])
    op.create_table(
        "ai_chat_model_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider_config_id", sa.Integer(), sa.ForeignKey("ai_chat_provider_configs.id"), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("model_type", sa.String(32), nullable=False, server_default="chat"),
        sa.Column("supports_image_input", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("context_window_tokens", sa.Integer(), nullable=False, server_default="200000"),
        sa.Column("history_token_ratio", sa.Float(), nullable=False, server_default="1"),
        sa.Column("advanced_config_json", sa.JSON(), nullable=False),
        sa.Column("model_capability_json", sa.JSON(), nullable=False),
        sa.Column("capability_override_json", sa.JSON(), nullable=False),
        sa.Column("catalog_provider_key", sa.String(128), nullable=True),
        sa.Column("catalog_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        *_audit(), *_timestamps(),
    )
    for column in ("user_id", "scope", "provider_config_id", "model_type", "catalog_provider_key", "status"):
        op.create_index(f"ix_ai_chat_model_configs_{column}", "ai_chat_model_configs", [column])
    op.create_table(
        "ai_chat_slot_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("slot", sa.String(64), nullable=False),
        sa.Column("llm_config_id", sa.Integer(), sa.ForeignKey("ai_chat_model_configs.id"), nullable=True),
        *_audit(), *_timestamps(),
    )
    for column in ("user_id", "scope", "llm_config_id"):
        op.create_index(f"ix_ai_chat_slot_bindings_{column}", "ai_chat_slot_bindings", [column])
    op.create_index("uq_ai_chat_slot_bindings_personal_user_slot", "ai_chat_slot_bindings", ["user_id", "slot"], unique=True, sqlite_where=sa.text("scope = 'personal'"), postgresql_where=sa.text("scope = 'personal'"))
    op.create_index("uq_ai_chat_slot_bindings_global_slot", "ai_chat_slot_bindings", ["slot"], unique=True, sqlite_where=sa.text("scope = 'global'"), postgresql_where=sa.text("scope = 'global'"))


def _create_image_tables() -> None:
    """创建图片供应商、模型和绑定表。"""

    op.create_table(
        "ai_image_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False), sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider_key", sa.String(64), nullable=False), sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True), sa.Column("status", sa.String(32), nullable=False),
        *_audit(), *_timestamps(),
    )
    for column in ("user_id", "scope", "provider_key", "status"):
        op.create_index(f"ix_ai_image_provider_configs_{column}", "ai_image_provider_configs", [column])
    op.create_table(
        "ai_image_model_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False), sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider_config_id", sa.Integer(), sa.ForeignKey("ai_image_provider_configs.id"), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=False), sa.Column("advanced_config_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), *_audit(), *_timestamps(),
    )
    for column in ("user_id", "scope", "provider_config_id", "status"):
        op.create_index(f"ix_ai_image_model_configs_{column}", "ai_image_model_configs", [column])
    op.create_table(
        "ai_image_slot_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False), sa.Column("slot", sa.String(64), nullable=False),
        sa.Column("model_config_id", sa.Integer(), sa.ForeignKey("ai_image_model_configs.id"), nullable=True),
        *_audit(), *_timestamps(),
    )
    for column in ("user_id", "scope", "model_config_id"):
        op.create_index(f"ix_ai_image_slot_bindings_{column}", "ai_image_slot_bindings", [column])
    op.create_index("uq_ai_image_slot_bindings_personal_user_slot", "ai_image_slot_bindings", ["user_id", "slot"], unique=True, sqlite_where=sa.text("scope = 'personal'"), postgresql_where=sa.text("scope = 'personal'"))
    op.create_index("uq_ai_image_slot_bindings_global_slot", "ai_image_slot_bindings", ["slot"], unique=True, sqlite_where=sa.text("scope = 'global'"), postgresql_where=sa.text("scope = 'global'"))


def _create_image_job_table(*, model_table: str = "ai_image_model_configs") -> None:
    """按当前任务契约重建图片任务表并指向图片模型。"""

    op.create_table(
        "ai_image_generation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(128), nullable=False), sa.Column("run_id", sa.String(128), sa.ForeignKey("ai_agent_runs.run_id"), nullable=False),
        sa.Column("session_id", sa.String(128), sa.ForeignKey("ai_agent_sessions.session_id"), nullable=False),
        sa.Column("tool_call_id", sa.String(255), nullable=False), sa.Column("deferred_tool_call_id", sa.String(255), nullable=False),
        sa.Column("member_run_id", sa.String(128), sa.ForeignKey("ai_agent_member_runs.member_run_id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("model_config_id", sa.Integer(), sa.ForeignKey(f"{model_table}.id"), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False), sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("model_snapshot_json", sa.JSON(), nullable=False), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=True), sa.Column("provider_task_id", sa.String(255), nullable=True),
        sa.Column("provider_status", sa.String(64), nullable=True), sa.Column("provider_request_id", sa.String(255), nullable=True),
        sa.Column("provider_state_json", sa.JSON(), nullable=True), sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True), sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=True), sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True), sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True), sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True), sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), sa.Column("continued_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(), sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_image_generation_jobs_run_tool_call"),
    )
    for column in ("job_id", "run_id", "session_id", "tool_call_id", "deferred_tool_call_id", "member_run_id", "user_id", "workspace_id", "project_id", "model_config_id", "operation", "status", "provider_task_id", "provider_status", "next_poll_at", "worker_id", "lease_expires_at", "continued_at"):
        op.create_index(f"ix_ai_image_generation_jobs_{column}", "ai_image_generation_jobs", [column], unique=column == "job_id")


def _create_legacy_llm_tables() -> None:
    """为 downgrade 恢复空的旧表结构。"""

    op.create_table("ai_llm_provider_configs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("scope", sa.String(32), nullable=False), sa.Column("name", sa.String(128), nullable=False), sa.Column("provider_key", sa.String(64), nullable=False), sa.Column("base_url", sa.Text()), sa.Column("api_key_ciphertext", sa.Text()), sa.Column("status", sa.String(32), nullable=False), *_audit(), *_timestamps())
    op.create_table("ai_llm_configs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("scope", sa.String(32), nullable=False), sa.Column("name", sa.String(128), nullable=False), sa.Column("provider_config_id", sa.Integer(), sa.ForeignKey("ai_llm_provider_configs.id"), nullable=False), sa.Column("model_id", sa.String(255), nullable=False), sa.Column("model_type", sa.String(32), nullable=False), sa.Column("reasoning_mode", sa.String(32), nullable=False), sa.Column("reasoning_level", sa.String(32)), sa.Column("supports_image_input", sa.Boolean(), nullable=False), sa.Column("context_window_tokens", sa.Integer(), nullable=False), sa.Column("history_token_ratio", sa.Float(), nullable=False), sa.Column("advanced_config_json", sa.JSON(), nullable=False), sa.Column("model_capability_json", sa.JSON(), nullable=False), sa.Column("status", sa.String(32), nullable=False), *_audit(), *_timestamps())
    op.create_table("ai_llm_slot_bindings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("scope", sa.String(32), nullable=False), sa.Column("slot", sa.String(64), nullable=False), sa.Column("llm_config_id", sa.Integer(), sa.ForeignKey("ai_llm_configs.id")), *_audit(), *_timestamps())
    _create_image_job_table(model_table="ai_llm_configs")
