"""add workspace asset archive fields

Revision ID: 20260508_0042
Revises: 20260507_0041
Create Date: 2026-05-08 17:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260508_0042"
down_revision: str | None = "20260507_0041"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """为资源库增加归档、历史副本与来源资源字段。"""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'active'"),
            )
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("archive_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("source_asset_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("history_kind", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_workspace_assets_source_asset_id_workspace_assets",
            "workspace_assets",
            ["source_asset_id"],
            ["id"],
        )
        batch_op.create_index("ix_workspace_assets_status", ["status"])
        batch_op.create_index("ix_workspace_assets_source_asset_id", ["source_asset_id"])


def downgrade() -> None:
    """回滚资源归档与历史副本字段。"""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.drop_index("ix_workspace_assets_source_asset_id")
        batch_op.drop_index("ix_workspace_assets_status")
        batch_op.drop_constraint("fk_workspace_assets_source_asset_id_workspace_assets", type_="foreignkey")
        batch_op.drop_column("history_kind")
        batch_op.drop_column("source_asset_id")
        batch_op.drop_column("archive_reason")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("status")
