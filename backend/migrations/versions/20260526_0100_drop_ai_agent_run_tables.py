"""文件功能：移除旧自研智能体 run 任务与事件回放表。

Revision ID: 20260526_0100
Revises: 20260523_0059
Create Date: 2026-05-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260526_0100"
down_revision: Union[str, Sequence[str], None] = "20260523_0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """删除旧平台 run 状态表，运行事实源改由 Agno session/run/events 承担。"""

    op.drop_table("ai_agent_run_events")
    op.drop_table("ai_agent_run_tasks")


def downgrade() -> None:
    """回滚时恢复旧平台 run 状态表结构。"""

    op.create_table(
        "ai_agent_run_tasks",
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("backend_session_id", sa.String(length=64), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("input_payload_json", sa.JSON(), nullable=True),
        sa.Column("tool_scopes_json", sa.JSON(), nullable=True),
        sa.Column("tool_auth_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tool_auth_max_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("pending_requirement_json", sa.JSON(), nullable=True),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(op.f("ix_ai_agent_run_tasks_agent_id"), "ai_agent_run_tasks", ["agent_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_component_id"), "ai_agent_run_tasks", ["component_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_page_id"), "ai_agent_run_tasks", ["page_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_project_id"), "ai_agent_run_tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_run_id"), "ai_agent_run_tasks", ["run_id"], unique=True)
    op.create_index(op.f("ix_ai_agent_run_tasks_scope_type"), "ai_agent_run_tasks", ["scope_type"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_session_id"), "ai_agent_run_tasks", ["session_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_source"), "ai_agent_run_tasks", ["source"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_status"), "ai_agent_run_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_user_id"), "ai_agent_run_tasks", ["user_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_tasks_workspace_id"), "ai_agent_run_tasks", ["workspace_id"], unique=False)

    op.create_table(
        "ai_agent_run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["ai_agent_run_tasks.task_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence", name="uq_ai_agent_run_events_task_sequence"),
    )
    op.create_index(op.f("ix_ai_agent_run_events_event"), "ai_agent_run_events", ["event"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_events_run_id"), "ai_agent_run_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_ai_agent_run_events_task_id"), "ai_agent_run_events", ["task_id"], unique=False)
