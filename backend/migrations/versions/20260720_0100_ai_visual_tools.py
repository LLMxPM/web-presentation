"""文件功能：增加视觉模型类型、附件尺寸与持久化图片生成任务。

Revision ID: 20260720_0100
Revises: 20260712_0500
Create Date: 2026-07-20 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260720_0100"
down_revision: Union[str, Sequence[str], None] = "20260712_0500"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级视觉模型配置与图片任务结构。"""

    op.add_column(
        "ai_llm_configs",
        sa.Column("model_type", sa.String(length=32), server_default="chat", nullable=False),
    )
    op.create_index("ix_ai_llm_configs_model_type", "ai_llm_configs", ["model_type"])
    op.add_column("ai_agent_image_attachments", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("height", sa.Integer(), nullable=True))

    op.create_table(
        "ai_image_generation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("model_config_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("model_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("continued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["model_config_id"], ["ai_llm_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_image_generation_jobs_run_tool_call"),
    )
    for column in (
        "job_id", "run_id", "session_id", "tool_call_id", "user_id", "workspace_id",
        "project_id", "model_config_id", "operation", "status", "worker_id", "lease_expires_at", "continued_at",
    ):
        op.create_index(
            f"ix_ai_image_generation_jobs_{column}",
            "ai_image_generation_jobs",
            [column],
            unique=column == "job_id",
        )


def downgrade() -> None:
    """移除视觉模型配置与图片任务结构。"""

    op.drop_table("ai_image_generation_jobs")
    op.drop_column("ai_agent_image_attachments", "height")
    op.drop_column("ai_agent_image_attachments", "width")
    op.drop_index("ix_ai_llm_configs_model_type", table_name="ai_llm_configs")
    op.drop_column("ai_llm_configs", "model_type")
