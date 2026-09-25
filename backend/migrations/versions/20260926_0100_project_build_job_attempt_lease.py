"""文件功能：为项目整包构建任务补充 attempt 身份、租约与重试预算列。

Revision ID: 20260926_0100
Revises: 20260925_0100
Create Date: 2026-09-26 01:00:00.000000

新增列尽量可空或带服务端默认值，旧代码仍可读写本表；回退时先切旧代码再降级 schema。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260926_0100"
down_revision: Union[str, Sequence[str], None] = "20260925_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为构建任务补充 attempt、租约与重试预算列。"""

    op.add_column("project_build_jobs", sa.Column("attempt_id", sa.String(length=64), nullable=True))
    op.add_column(
        "project_build_jobs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "project_build_jobs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
    )
    op.add_column("project_build_jobs", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column(
        "project_build_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_build_jobs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_build_jobs",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_project_build_jobs_attempt_id", "project_build_jobs", ["attempt_id"])
    op.create_index("ix_project_build_jobs_lease_owner", "project_build_jobs", ["lease_owner"])
    op.create_index("ix_project_build_jobs_lease_expires_at", "project_build_jobs", ["lease_expires_at"])
    op.create_index(
        "ix_project_build_jobs_status_lease",
        "project_build_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    """移除构建任务 attempt 与租约列，回到无重试预算的旧形态。"""

    op.drop_index("ix_project_build_jobs_status_lease", table_name="project_build_jobs")
    op.drop_index("ix_project_build_jobs_lease_expires_at", table_name="project_build_jobs")
    op.drop_index("ix_project_build_jobs_lease_owner", table_name="project_build_jobs")
    op.drop_index("ix_project_build_jobs_attempt_id", table_name="project_build_jobs")
    op.drop_column("project_build_jobs", "deadline_at")
    op.drop_column("project_build_jobs", "claimed_at")
    op.drop_column("project_build_jobs", "lease_expires_at")
    op.drop_column("project_build_jobs", "lease_owner")
    op.drop_column("project_build_jobs", "max_attempts")
    op.drop_column("project_build_jobs", "attempt_count")
    op.drop_column("project_build_jobs", "attempt_id")
