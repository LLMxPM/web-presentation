"""文件功能：新增资源渲染提示回填任务表。

Revision ID: 20260701_0100
Revises: 20260626_0111
Create Date: 2026-07-01 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260701_0100"
down_revision: Union[str, Sequence[str], None] = "20260626_0111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建资源渲染提示回填任务表。"""

    op.create_table(
        "asset_render_hint_backfill_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_group_id", sa.String(length=64), nullable=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("overwrite_manual", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("current_render_metadata", sa.JSON(), nullable=True),
        sa.Column("next_render_metadata", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["workspace_assets.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_render_hint_backfill_jobs_asset_id", "asset_render_hint_backfill_jobs", ["asset_id"])
    op.create_index("ix_asset_render_hint_backfill_jobs_asset_type", "asset_render_hint_backfill_jobs", ["asset_type"])
    op.create_index(
        "ix_asset_render_hint_backfill_jobs_dedupe_active",
        "asset_render_hint_backfill_jobs",
        ["asset_id", "mode", "overwrite_manual", "status"],
    )
    op.create_index("ix_asset_render_hint_backfill_jobs_job_group_id", "asset_render_hint_backfill_jobs", ["job_group_id"])
    op.create_index("ix_asset_render_hint_backfill_jobs_mode", "asset_render_hint_backfill_jobs", ["mode"])
    op.create_index("ix_asset_render_hint_backfill_jobs_source", "asset_render_hint_backfill_jobs", ["source"])
    op.create_index("ix_asset_render_hint_backfill_jobs_status", "asset_render_hint_backfill_jobs", ["status"])
    op.create_index("ix_asset_render_hint_backfill_jobs_workspace_id", "asset_render_hint_backfill_jobs", ["workspace_id"])


def downgrade() -> None:
    """删除资源渲染提示回填任务表。"""

    op.drop_index("ix_asset_render_hint_backfill_jobs_workspace_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_status", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_source", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_mode", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_job_group_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_dedupe_active", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_asset_type", table_name="asset_render_hint_backfill_jobs")
    op.drop_index("ix_asset_render_hint_backfill_jobs_asset_id", table_name="asset_render_hint_backfill_jobs")
    op.drop_table("asset_render_hint_backfill_jobs")
