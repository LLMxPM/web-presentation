"""文件功能：为页面截图记录生成时的展示配置指纹。

Revision ID: 20260516_0054
Revises: 20260514_0053
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260516_0054"
down_revision: str | None = "20260514_0053"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    """检查表中是否存在目标列，兼容重复执行与测试库。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """新增截图配置指纹字段。"""

    if not _has_column("pages", "screenshot_config_hash"):
        with op.batch_alter_table("pages") as batch_op:
            batch_op.add_column(sa.Column("screenshot_config_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """移除截图配置指纹字段。"""

    if _has_column("pages", "screenshot_config_hash"):
        with op.batch_alter_table("pages") as batch_op:
            batch_op.drop_column("screenshot_config_hash")
