"""新增智能体后台运行任务与事件回放表。

Revision ID: 20260505_0037
Revises: 20260505_0036
Create Date: 2026-05-05 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260505_0037"
down_revision: str | None = "20260505_0036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """创建后台 run 任务索引表与规范化事件回放表。"""

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


def downgrade() -> None:
    """删除后台 run 任务与事件回放表。"""

    op.drop_index("ix_ai_agent_run_events_task_id", table_name="ai_agent_run_events")
    op.drop_index("ix_ai_agent_run_events_event", table_name="ai_agent_run_events")
    op.drop_table("ai_agent_run_events")
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
