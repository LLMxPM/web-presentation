"""文件功能：为用户级大模型配置增加受管的思考强度字段。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260511_0049"
down_revision: str | None = "20260510_0048"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    """检查当前数据库是否存在指定表。"""

    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查指定字段是否存在，避免部分开发库重复迁移失败。"""

    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """增加 thinking_effort 字段，由运行时按供应商映射为实际参数。"""

    if _has_column("ai_llm_configs", "thinking_effort"):
        return
    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.add_column(sa.Column("thinking_effort", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """移除 thinking_effort 字段。"""

    if not _has_column("ai_llm_configs", "thinking_effort"):
        return
    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.drop_column("thinking_effort")
