"""文件功能：新增 system_settings 系统配置表，支持类 B 业务配置持久化与双方言兼容。

Revision ID: 20261002_0100
Revises: 20260930_0300
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.types import JSONPayload, UTCDateTime

revision = "20261002_0100"
down_revision = "20260930_0300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 system_settings 表与分类索引。"""
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", JSONPayload, nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_system_settings_category", "system_settings", ["category"])


def downgrade() -> None:
    """删除 system_settings 表与分类索引。"""
    op.drop_index("ix_system_settings_category", table_name="system_settings")
    op.drop_table("system_settings")
