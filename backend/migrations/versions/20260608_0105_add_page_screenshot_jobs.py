"""文件功能：新增页面截图异步任务表。

Revision ID: 20260608_0105
Revises: 20260606_0104
Create Date: 2026-06-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260608_0105"
down_revision: Union[str, Sequence[str], None] = "20260606_0104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建页面截图异步任务表。"""

    op.create_table(
        "page_screenshot_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_group_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("viewport_width", sa.Integer(), nullable=False),
        sa.Column("viewport_height", sa.Integer(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_screenshot_jobs_config_hash", "page_screenshot_jobs", ["config_hash"])
    op.create_index("ix_page_screenshot_jobs_job_group_id", "page_screenshot_jobs", ["job_group_id"])
    op.create_index("ix_page_screenshot_jobs_page_id", "page_screenshot_jobs", ["page_id"])
    op.create_index("ix_page_screenshot_jobs_project_id", "page_screenshot_jobs", ["project_id"])
    op.create_index("ix_page_screenshot_jobs_source", "page_screenshot_jobs", ["source"])
    op.create_index("ix_page_screenshot_jobs_status", "page_screenshot_jobs", ["status"])
    op.create_index("ix_page_screenshot_jobs_workspace_id", "page_screenshot_jobs", ["workspace_id"])
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height", "status"],
    )


def downgrade() -> None:
    """删除页面截图异步任务表。"""

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_workspace_id", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_status", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_source", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_project_id", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_page_id", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_job_group_id", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_config_hash", table_name="page_screenshot_jobs")
    op.drop_table("page_screenshot_jobs")
