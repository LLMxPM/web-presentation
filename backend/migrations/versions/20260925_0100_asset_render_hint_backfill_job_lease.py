"""文件功能：为资源比例回填任务补充数据库租约列，使领取与迟到结果围栏不再依赖运行态锁。

Revision ID: 20260925_0100
Revises: 20260910_0100
Create Date: 2026-09-25 01:00:00.000000

新增列全部可为空，旧代码仍可读写本表；回退时先切旧代码再降级 schema。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260925_0100"
down_revision: Union[str, Sequence[str], None] = "20260910_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为回填任务补充 worker 身份、租约与心跳列。"""

    op.add_column("asset_render_hint_backfill_jobs", sa.Column("worker_id", sa.String(length=128), nullable=True))
    op.add_column(
        "asset_render_hint_backfill_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_render_hint_backfill_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_render_hint_backfill_jobs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_asset_render_hint_backfill_jobs_worker_id",
        "asset_render_hint_backfill_jobs",
        ["worker_id"],
    )
    op.create_index(
        "ix_asset_render_hint_backfill_jobs_lease_expires_at",
        "asset_render_hint_backfill_jobs",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_asset_render_hint_backfill_jobs_status_lease",
        "asset_render_hint_backfill_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    """移除回填任务租约列与索引，回到仅按运行态锁领取的形态。"""

    op.drop_index("ix_asset_render_hint_backfill_jobs_status_lease", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_lease_expires_at", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_worker_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_column("asset_render_hint_backfill_jobs", "cancel_requested_at")
    op.drop_column("asset_render_hint_backfill_jobs", "heartbeat_at")
    op.drop_column("asset_render_hint_backfill_jobs", "lease_expires_at")
    op.drop_column("asset_render_hint_backfill_jobs", "worker_id")