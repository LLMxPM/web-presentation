"""移除工作空间级组件预览默认配置。

Revision ID: 20260505_0036
Revises: 20260429_0035
Create Date: 2026-05-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260505_0036"
down_revision: str | None = "20260429_0035"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """删除不再参与组件预览的工作空间默认配置字段。"""

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("component_preview_default_config")


def downgrade() -> None:
    """回滚时恢复旧字段，仅保留空对象默认值。"""

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("component_preview_default_config", sa.JSON(), nullable=True))
    op.execute("UPDATE workspaces SET component_preview_default_config = '{}' WHERE component_preview_default_config IS NULL")
    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.alter_column("component_preview_default_config", existing_type=sa.JSON(), nullable=False)
