"""add workspace font configs

Revision ID: 20260411_0011
Revises: 20260411_0010
Create Date: 2026-04-11 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260411_0011"
down_revision: str | None = "20260411_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """创建工作空间字体注册表。"""

    op.create_table(
        "workspace_font_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("asset_name", sa.String(length=255), nullable=False),
        sa.Column("font_family", sa.String(length=255), nullable=False),
        sa.Column("font_format", sa.String(length=32), nullable=False),
        sa.Column("font_weight", sa.String(length=32), nullable=False, server_default="400"),
        sa.Column("font_style", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("font_display", sa.String(length=32), nullable=False, server_default="swap"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["workspace_assets.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "asset_id", name="uq_workspace_font_configs_workspace_asset"),
        sa.UniqueConstraint("workspace_id", "asset_name", name="uq_workspace_font_configs_workspace_asset_name"),
    )
    op.create_index(op.f("ix_workspace_font_configs_workspace_id"), "workspace_font_configs", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_workspace_font_configs_asset_id"), "workspace_font_configs", ["asset_id"], unique=False)


def downgrade() -> None:
    """删除工作空间字体注册表。"""

    op.drop_index(op.f("ix_workspace_font_configs_asset_id"), table_name="workspace_font_configs")
    op.drop_index(op.f("ix_workspace_font_configs_workspace_id"), table_name="workspace_font_configs")
    op.drop_table("workspace_font_configs")
