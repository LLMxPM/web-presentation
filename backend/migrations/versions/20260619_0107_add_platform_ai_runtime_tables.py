"""文件功能：新增平台自有智能体会话、运行、事件与 HITL 运行态表。

Revision ID: 20260619_0107
Revises: 20260609_0106
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260619_0107"
down_revision: Union[str, Sequence[str], None] = "20260609_0106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建平台自有智能体运行态表。"""

    op.create_table(
        "ai_agent_sessions",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_name", sa.String(length=128), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["workspace_components.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("session_id"),
    )
    for column in (
        "agent_id",
        "user_id",
        "scope_type",
        "workspace_id",
        "project_id",
        "page_id",
        "component_id",
        "source",
        "deleted_at",
    ):
        op.create_index(f"ix_ai_agent_sessions_{column}", "ai_agent_sessions", [column])

    op.create_table(
        "ai_agent_runs",
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("input_payload_json", sa.JSON(), nullable=False),
        sa.Column("message_history_json", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("reasoning_content", sa.Text(), nullable=True),
        sa.Column("pending_requirement_json", sa.JSON(), nullable=True),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["workspace_components.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    for column in (
        "session_id",
        "agent_id",
        "user_id",
        "status",
        "scope_type",
        "workspace_id",
        "project_id",
        "page_id",
        "component_id",
        "source",
    ):
        op.create_index(f"ix_ai_agent_runs_{column}", "ai_agent_runs", [column])

    op.create_table(
        "ai_agent_run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "event_index", name="uq_ai_agent_run_events_run_index"),
    )
    op.create_index("ix_ai_agent_run_events_event", "ai_agent_run_events", ["event"])
    op.create_index("ix_ai_agent_run_events_run_id", "ai_agent_run_events", ["run_id"])
    op.create_index("ix_ai_agent_run_events_session_id", "ai_agent_run_events", ["session_id"])

    op.create_table(
        "ai_agent_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("reasoning_content", sa.Text(), nullable=True),
        sa.Column("message_json", sa.JSON(), nullable=True),
        sa.Column("attachments_json", sa.JSON(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("session_id", "run_id", "role"):
        op.create_index(f"ix_ai_agent_messages_{column}", "ai_agent_messages", [column])

    op.create_table(
        "ai_agent_tool_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("member_run_id", sa.String(length=128), nullable=True),
        sa.Column("tool_call_id", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("input_payload_json", sa.JSON(), nullable=True),
        sa.Column("output_payload_json", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_agent_tool_calls_run_tool_call"),
    )
    for column in ("session_id", "run_id", "member_run_id", "tool_call_id", "tool_name", "status"):
        op.create_index(f"ix_ai_agent_tool_calls_{column}", "ai_agent_tool_calls", [column])

    op.create_table(
        "ai_agent_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("requirement_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("member_agent_id", sa.String(length=128), nullable=True),
        sa.Column("member_agent_name", sa.String(length=128), nullable=True),
        sa.Column("member_run_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("resolved_payload_json", sa.JSON(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("requirement_id", "session_id", "run_id", "kind", "status", "tool_call_id", "tool_name", "member_run_id"):
        op.create_index(f"ix_ai_agent_requirements_{column}", "ai_agent_requirements", [column], unique=column == "requirement_id")

    op.create_table(
        "ai_agent_member_runs",
        sa.Column("member_run_id", sa.String(length=128), nullable=False),
        sa.Column("parent_run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delegate_tool_call_id", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("member_run_id"),
    )
    for column in ("parent_run_id", "session_id", "agent_id", "status", "delegate_tool_call_id"):
        op.create_index(f"ix_ai_agent_member_runs_{column}", "ai_agent_member_runs", [column])


def downgrade() -> None:
    """删除平台自有智能体运行态表。"""

    op.drop_table("ai_agent_member_runs")
    op.drop_table("ai_agent_requirements")
    op.drop_table("ai_agent_tool_calls")
    op.drop_table("ai_agent_messages")
    op.drop_table("ai_agent_run_events")
    op.drop_table("ai_agent_runs")
    op.drop_table("ai_agent_sessions")
