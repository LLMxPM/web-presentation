"""文件功能：移除未开放的时刻截图选择器与采样回执，恢复静态输入活动去重。

Revision ID: 20261029_0100
Revises: 20261021_0100
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261029_0100"
down_revision = "20261021_0100"
branch_labels = None
depends_on = None

_TABLE = "page_screenshot_jobs"
_INDEX = "ix_page_screenshot_jobs_dedupe_active"
_KEYS = ["page_id", "target_page_version_no", "config_hash", "viewport_width", "viewport_height"]
_ACTIVE = sa.text("status IN ('pending', 'running')")


def upgrade() -> None:
    """先终止开发遗留选择器任务，再移除字段；保留 PNG 引用、默认指针与发布围栏列。"""
    jobs = sa.table(_TABLE, sa.column("motion_snapshot_json"), sa.column("status"),
                    sa.column("error_code"), sa.column("error_message"), sa.column("finished_at"),
                    sa.column("lease_expires_at"), sa.column("heartbeat_at"))
    op.execute(jobs.update().where(jobs.c.motion_snapshot_json.is_not(None),
                                  sa.cast(jobs.c.motion_snapshot_json, sa.Text()) != "null",
                                  jobs.c.status.in_(["pending", "running"])).values(
        status="cancelled", error_code="SCREENSHOT_SELECTOR_REMOVED",
        error_message="指定动画时刻截图已移除，请创建独立静态截图任务。",
        finished_at=sa.func.current_timestamp(), lease_expires_at=None, heartbeat_at=None,
    ))
    op.drop_index(_INDEX, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("motion_snapshot_json")
        batch.drop_column("motion_snapshot_hash")
        batch.drop_column("result_applied_motion_json")
    op.create_index(_INDEX, _TABLE, _KEYS, unique=True, sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)


def downgrade() -> None:
    """恢复旧结构供代码回退；不重建已删除的选择器内容或重启已取消任务。"""
    op.drop_index(_INDEX, table_name=_TABLE)
    op.add_column(_TABLE, sa.Column("motion_snapshot_json", sa.JSON(), nullable=True))
    op.add_column(_TABLE, sa.Column("motion_snapshot_hash", sa.String(64), nullable=False, server_default=""))
    op.add_column(_TABLE, sa.Column("result_applied_motion_json", sa.JSON(), nullable=True))
    op.create_index(_INDEX, _TABLE, [*_KEYS, "motion_snapshot_hash"], unique=True,
                    sqlite_where=_ACTIVE, postgresql_where=_ACTIVE)
