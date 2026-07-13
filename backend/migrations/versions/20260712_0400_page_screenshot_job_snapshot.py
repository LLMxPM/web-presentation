"""文件功能：为截图任务固化目标页面版本，并把活动去重范围扩展到版本快照。

Revision ID: 20260712_0400
Revises: 20260712_0300
Create Date: 2026-07-12 04:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260712_0400"
down_revision: Union[str, Sequence[str], None] = "20260712_0300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """回填历史任务版本，并让不同页面版本的活动任务可独立收敛。"""

    op.add_column("page_screenshot_jobs", sa.Column("target_page_version_no", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE page_screenshot_jobs
            SET target_page_version_no = COALESCE(
                (
                    SELECT pages.current_version_no
                    FROM pages
                    WHERE pages.id = page_screenshot_jobs.page_id
                ),
                1
            )
            WHERE target_page_version_no IS NULL
            """
        )
    )
    with op.batch_alter_table("page_screenshot_jobs") as batch_op:
        batch_op.alter_column("target_page_version_no", existing_type=sa.Integer(), nullable=False)

    op.create_index(
        "ix_page_screenshot_jobs_target_page_version_no",
        "page_screenshot_jobs",
        ["target_page_version_no"],
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "target_page_version_no", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    """移除截图任务版本快照字段，恢复上一版活动去重索引。"""

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )
    op.drop_index("ix_page_screenshot_jobs_target_page_version_no", table_name="page_screenshot_jobs")
    with op.batch_alter_table("page_screenshot_jobs") as batch_op:
        batch_op.drop_column("target_page_version_no")
