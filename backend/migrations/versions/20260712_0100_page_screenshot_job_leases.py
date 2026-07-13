"""文件功能：为页面截图任务增加数据库租约、取消状态和可复用的任务组成员关系。

Revision ID: 20260712_0100
Revises: 20260701_0100
Create Date: 2026-07-12 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260712_0100"
down_revision: Union[str, Sequence[str], None] = "20260701_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加截图任务租约字段、任务组表，并把历史单组关系回填为成员关系。"""

    op.add_column("page_screenshot_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_page_screenshot_jobs_worker_id", "page_screenshot_jobs", ["worker_id"])
    op.create_index("ix_page_screenshot_jobs_lease_expires_at", "page_screenshot_jobs", ["lease_expires_at"])

    op.create_table(
        "page_screenshot_job_groups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_screenshot_job_groups_workspace_id", "page_screenshot_job_groups", ["workspace_id"])
    op.create_index("ix_page_screenshot_job_groups_project_id", "page_screenshot_job_groups", ["project_id"])
    op.create_table(
        "page_screenshot_job_group_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["page_screenshot_job_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["page_screenshot_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "job_id", name="uq_page_screenshot_job_group_items_group_job"),
    )
    op.create_index("ix_page_screenshot_job_group_items_group_id", "page_screenshot_job_group_items", ["group_id"])
    op.create_index("ix_page_screenshot_job_group_items_job_id", "page_screenshot_job_group_items", ["job_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO page_screenshot_job_groups
                (id, source, workspace_id, project_id, created_by, created_at, updated_at)
            SELECT
                job_group_id,
                MIN(source),
                MIN(workspace_id),
                MIN(project_id),
                MIN(created_by),
                MIN(created_at),
                MAX(updated_at)
            FROM page_screenshot_jobs
            WHERE job_group_id IS NOT NULL
            GROUP BY job_group_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO page_screenshot_job_group_items (group_id, job_id, created_at)
            SELECT job_group_id, id, created_at
            FROM page_screenshot_jobs
            WHERE job_group_id IS NOT NULL
            """
        )
    )

    # 旧版本没有数据库租约；升级后的 running 任务应由新恢复逻辑安全重排。
    op.execute(
        sa.text(
            """
            UPDATE page_screenshot_jobs
            SET lease_expires_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
            """
        )
    )

    # 建立活动任务唯一索引前，先收敛历史上可能已经重复的 pending/running 记录。
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY page_id, config_hash, viewport_width, viewport_height
                        ORDER BY created_at ASC, id ASC
                    ) AS row_no
                FROM page_screenshot_jobs
                WHERE status IN ('pending', 'running')
            )
            UPDATE page_screenshot_jobs
            SET
                status = 'failed',
                error_code = 'PAGE_SCREENSHOT_JOB_DEDUPED',
                error_message = '升级时合并了重复的活动截图任务。',
                finished_at = CURRENT_TIMESTAMP,
                lease_expires_at = NULL,
                heartbeat_at = NULL
            WHERE id IN (SELECT id FROM ranked WHERE row_no > 1)
            """
        )
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    """恢复截图任务旧索引并删除租约和多任务组结构。"""

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height", "status"],
    )
    op.drop_index("ix_page_screenshot_job_group_items_job_id", table_name="page_screenshot_job_group_items")
    op.drop_index("ix_page_screenshot_job_group_items_group_id", table_name="page_screenshot_job_group_items")
    op.drop_table("page_screenshot_job_group_items")
    op.drop_index("ix_page_screenshot_job_groups_project_id", table_name="page_screenshot_job_groups")
    op.drop_index("ix_page_screenshot_job_groups_workspace_id", table_name="page_screenshot_job_groups")
    op.drop_table("page_screenshot_job_groups")
    op.drop_index("ix_page_screenshot_jobs_lease_expires_at", table_name="page_screenshot_jobs")
    op.drop_index("ix_page_screenshot_jobs_worker_id", table_name="page_screenshot_jobs")
    op.drop_column("page_screenshot_jobs", "cancel_requested_at")
    op.drop_column("page_screenshot_jobs", "heartbeat_at")
    op.drop_column("page_screenshot_jobs", "lease_expires_at")
    op.drop_column("page_screenshot_jobs", "worker_id")
