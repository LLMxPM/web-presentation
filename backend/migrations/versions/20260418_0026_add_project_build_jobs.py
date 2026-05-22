"""add project build jobs

Revision ID: 20260418_0026
Revises: 20260418_0025
Create Date: 2026-04-18 21:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260418_0026"
down_revision: str | None = "20260418_0025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增项目整包构建任务表。"""

    op.create_table(
        "project_build_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("snapshot_release_id", sa.Integer(), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("artifact_archive_path", sa.Text(), nullable=True),
        sa.Column("artifact_download_url", sa.Text(), nullable=True),
        sa.Column("artifact_entry_file", sa.String(length=255), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=128), nullable=True),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_project_build_jobs_project_id", "project_build_jobs", ["project_id"])
    op.create_index("ix_project_build_jobs_snapshot_release_id", "project_build_jobs", ["snapshot_release_id"])
    op.create_index("ix_project_build_jobs_status", "project_build_jobs", ["status"])


def downgrade() -> None:
    """回滚项目整包构建任务表。"""

    op.drop_index("ix_project_build_jobs_status", table_name="project_build_jobs")
    op.drop_index("ix_project_build_jobs_snapshot_release_id", table_name="project_build_jobs")
    op.drop_index("ix_project_build_jobs_project_id", table_name="project_build_jobs")
    op.drop_table("project_build_jobs")
