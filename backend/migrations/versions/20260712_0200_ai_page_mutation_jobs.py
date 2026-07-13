"""文件功能：新增 AI 页面变更批次与持久化任务表。

Revision ID: 20260712_0200
Revises: 20260712_0100
Create Date: 2026-07-12 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_0200"
down_revision: Union[str, Sequence[str], None] = "20260712_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 AI 页面变更批次、任务及其租约索引。"""

    op.create_table(
        "ai_page_mutation_batches",
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("run_step", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requirement_id", sa.String(length=128), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.PrimaryKeyConstraint("batch_id"),
        sa.UniqueConstraint("run_id", "run_step", name="uq_ai_page_mutation_batches_run_step"),
    )
    for column in ("run_id", "session_id", "status", "requirement_id", "worker_id", "lease_expires_at"):
        op.create_index(f"ix_ai_page_mutation_batches_{column}", "ai_page_mutation_batches", [column])

    op.create_table(
        "ai_page_mutation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("base_version_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["ai_page_mutation_batches.batch_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["ai_agent_runs.run_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["ai_agent_sessions.session_id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "tool_call_id", name="uq_ai_page_mutation_jobs_run_tool_call"),
    )
    for column in (
        "job_id", "batch_id", "run_id", "session_id", "tool_call_id", "operation", "workspace_id",
        "project_id", "page_id", "status", "worker_id", "lease_expires_at",
    ):
        # ORM 为 job_id 声明了 unique=True 与 index=True，SQLite 会把它表示为
        # 命名唯一索引而不是额外的 UNIQUE constraint；迁移必须保持同一结构，
        # 避免自动生成把非唯一索引反复替换为唯一索引。
        op.create_index(
            f"ix_ai_page_mutation_jobs_{column}",
            "ai_page_mutation_jobs",
            [column],
            unique=column == "job_id",
        )


def downgrade() -> None:
    """删除 AI 页面变更任务与批次表。"""

    op.drop_table("ai_page_mutation_jobs")
    op.drop_table("ai_page_mutation_batches")
