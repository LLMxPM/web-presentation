"""文件功能：为页面截图任务增加临时时间轴选择器与成功结果摘要，并扩展活动去重索引。

Revision ID: 20261021_0100
Revises: 20261019_0100
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261021_0100"
down_revision = "20261019_0100"
branch_labels = None
depends_on = None

_DEDUPE_PREDICATE = sa.text("status IN ('pending', 'running')")


def upgrade() -> None:
    """新增选择器与结果列；历史任务按默认 poster 处理，不改变现有指针。"""

    op.add_column("page_screenshot_jobs", sa.Column("motion_snapshot_json", sa.JSON(), nullable=True))
    op.add_column(
        "page_screenshot_jobs",
        sa.Column("motion_snapshot_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column("page_screenshot_jobs", sa.Column("result_storage_key", sa.String(512), nullable=True))
    op.add_column("page_screenshot_jobs", sa.Column("result_sha256", sa.String(64), nullable=True))
    op.add_column(
        "page_screenshot_jobs",
        sa.Column("result_applied_motion_json", sa.JSON(), nullable=True),
    )
    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        [
            "page_id",
            "target_page_version_no",
            "config_hash",
            "viewport_width",
            "viewport_height",
            "motion_snapshot_hash",
        ],
        unique=True,
        sqlite_where=_DEDUPE_PREDICATE,
        postgresql_where=_DEDUPE_PREDICATE,
    )


def downgrade() -> None:
    """移除临时选择器与结果列；已存 PNG 由存储运维保留，降级不删除业务文件。"""

    op.drop_index("ix_page_screenshot_jobs_dedupe_active", table_name="page_screenshot_jobs")
    op.create_index(
        "ix_page_screenshot_jobs_dedupe_active",
        "page_screenshot_jobs",
        ["page_id", "target_page_version_no", "config_hash", "viewport_width", "viewport_height"],
        unique=True,
        sqlite_where=_DEDUPE_PREDICATE,
        postgresql_where=_DEDUPE_PREDICATE,
    )
    for column in (
        "result_applied_motion_json",
        "result_sha256",
        "result_storage_key",
        "motion_snapshot_hash",
        "motion_snapshot_json",
    ):
        op.drop_column("page_screenshot_jobs", column)
