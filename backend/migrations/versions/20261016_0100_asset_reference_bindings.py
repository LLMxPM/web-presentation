"""文件功能：新增 asset_reference_bindings 资源占用绑定表，保护在途任务与产物引用的资源文件不被删除。

Revision ID: 20261016_0100
Revises: 20261002_0100
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.types import UTCDateTime

revision = "20261016_0100"
down_revision = "20261002_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建资源占用绑定表、唯一约束与检索索引。"""
    op.create_table(
        "asset_reference_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("owner_kind", sa.String(32), nullable=False),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("resource_name", sa.String(255), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("workspace_assets.id"), nullable=False),
        sa.Column("file_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("created_at", UTCDateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_kind", "owner_key", "resource_name", name="uq_asset_reference_bindings_owner_resource"),
    )
    op.create_index("ix_asset_reference_bindings_workspace_id", "asset_reference_bindings", ["workspace_id"])
    op.create_index("ix_asset_reference_bindings_asset_id", "asset_reference_bindings", ["asset_id"])
    op.create_index("ix_asset_reference_bindings_expires_at", "asset_reference_bindings", ["expires_at"])
    op.create_index(
        "ix_asset_reference_bindings_workspace_owner",
        "asset_reference_bindings",
        ["workspace_id", "owner_kind"],
    )


def downgrade() -> None:
    """删除资源占用绑定表与索引。"""
    op.drop_index("ix_asset_reference_bindings_workspace_owner", table_name="asset_reference_bindings")
    op.drop_index("ix_asset_reference_bindings_expires_at", table_name="asset_reference_bindings")
    op.drop_index("ix_asset_reference_bindings_asset_id", table_name="asset_reference_bindings")
    op.drop_index("ix_asset_reference_bindings_workspace_id", table_name="asset_reference_bindings")
    op.drop_table("asset_reference_bindings")
