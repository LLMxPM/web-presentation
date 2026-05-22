"""文件功能：切换 AI 会话链路为 Agno session-first，并移除后台 task 表。

Revision ID: 20260507_0041
Revises: 20260507_0040
Create Date: 2026-05-07 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260507_0041"
down_revision: str | None = "20260507_0040"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    """检查当前数据库是否存在指定表，兼容部分环境已手工清理的情况。"""

    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查指定表是否存在字段，避免重复迁移导致失败。"""

    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """新增模型上下文配置，并删除自定义后台 run task 与事件回放表。"""

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        if not _has_column("ai_llm_configs", "context_window_tokens"):
            batch_op.add_column(sa.Column("context_window_tokens", sa.Integer(), nullable=False, server_default=sa.text("32768")))
        if not _has_column("ai_llm_configs", "max_output_tokens"):
            batch_op.add_column(sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default=sa.text("4096")))
        if not _has_column("ai_llm_configs", "history_token_ratio"):
            batch_op.add_column(sa.Column("history_token_ratio", sa.Float(), nullable=False, server_default=sa.text("0.5")))

    if _has_table("ai_agent_run_events"):
        op.drop_index("ix_ai_agent_run_events_task_id", table_name="ai_agent_run_events")
        op.drop_index("ix_ai_agent_run_events_event", table_name="ai_agent_run_events")
        op.drop_table("ai_agent_run_events")

    if _has_table("ai_agent_run_tasks"):
        op.drop_index("ix_ai_agent_run_tasks_workspace_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_status", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_source", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_session_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_scope_type", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_project_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_page_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_component_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_agno_run_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_agent_id", table_name="ai_agent_run_tasks")
        op.drop_index("ix_ai_agent_run_tasks_admin_user_id", table_name="ai_agent_run_tasks")
        op.drop_table("ai_agent_run_tasks")


def downgrade() -> None:
    """回滚时恢复旧 task 表结构并移除上下文配置字段。"""

    if not _has_table("ai_agent_run_tasks"):
        op.create_table(
            "ai_agent_run_tasks",
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("agno_run_id", sa.String(length=128), nullable=True),
            sa.Column("session_id", sa.String(length=128), nullable=False),
            sa.Column("agent_id", sa.String(length=128), nullable=False),
            sa.Column("admin_user_id", sa.Integer(), nullable=False),
            sa.Column("backend_session_id", sa.String(length=64), nullable=True),
            sa.Column("scope_type", sa.String(length=32), nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("page_id", sa.Integer(), nullable=True),
            sa.Column("component_id", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_summary", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("pending_requirement_json", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"]),
            sa.PrimaryKeyConstraint("task_id"),
        )
        op.create_index("ix_ai_agent_run_tasks_admin_user_id", "ai_agent_run_tasks", ["admin_user_id"])
        op.create_index("ix_ai_agent_run_tasks_agent_id", "ai_agent_run_tasks", ["agent_id"])
        op.create_index("ix_ai_agent_run_tasks_agno_run_id", "ai_agent_run_tasks", ["agno_run_id"])
        op.create_index("ix_ai_agent_run_tasks_component_id", "ai_agent_run_tasks", ["component_id"])
        op.create_index("ix_ai_agent_run_tasks_page_id", "ai_agent_run_tasks", ["page_id"])
        op.create_index("ix_ai_agent_run_tasks_project_id", "ai_agent_run_tasks", ["project_id"])
        op.create_index("ix_ai_agent_run_tasks_scope_type", "ai_agent_run_tasks", ["scope_type"])
        op.create_index("ix_ai_agent_run_tasks_session_id", "ai_agent_run_tasks", ["session_id"])
        op.create_index("ix_ai_agent_run_tasks_source", "ai_agent_run_tasks", ["source"])
        op.create_index("ix_ai_agent_run_tasks_status", "ai_agent_run_tasks", ["status"])
        op.create_index("ix_ai_agent_run_tasks_workspace_id", "ai_agent_run_tasks", ["workspace_id"])

    if not _has_table("ai_agent_run_events"):
        op.create_table(
            "ai_agent_run_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("event", sa.String(length=128), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["ai_agent_run_tasks.task_id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", "sequence", name="uq_ai_agent_run_events_task_sequence"),
        )
        op.create_index("ix_ai_agent_run_events_event", "ai_agent_run_events", ["event"])
        op.create_index("ix_ai_agent_run_events_task_id", "ai_agent_run_events", ["task_id"])

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        if _has_column("ai_llm_configs", "history_token_ratio"):
            batch_op.drop_column("history_token_ratio")
        if _has_column("ai_llm_configs", "max_output_tokens"):
            batch_op.drop_column("max_output_tokens")
        if _has_column("ai_llm_configs", "context_window_tokens"):
            batch_op.drop_column("context_window_tokens")
