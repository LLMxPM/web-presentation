"""文件功能：为用户级智能体配置增加描述覆盖字段。

Revision ID: 20260513_0051
Revises: 20260513_0050
Create Date: 2026-05-13 20:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260513_0051"
down_revision: str | None = "20260513_0050"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    """检查当前数据库表是否包含指定列，兼容重复执行与测试库。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """增加 Agent 描述覆盖字段。"""

    if not _has_column("ai_agent_user_configs", "description_override"):
        with op.batch_alter_table("ai_agent_user_configs") as batch_op:
            batch_op.add_column(sa.Column("description_override", sa.Text(), nullable=True))


def downgrade() -> None:
    """移除 Agent 描述覆盖字段。"""

    if _has_column("ai_agent_user_configs", "description_override"):
        with op.batch_alter_table("ai_agent_user_configs") as batch_op:
            batch_op.drop_column("description_override")
