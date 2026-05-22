"""文件功能：为用户级大模型配置增加上下文压缩目标比例字段。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260509_0044"
down_revision: str | None = "20260509_0043"
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
    """增加压缩目标比例字段，默认压缩到模型窗口约 10%。"""

    if _has_column("ai_llm_configs", "compression_target_ratio"):
        return
    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "compression_target_ratio",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.1"),
            )
        )


def downgrade() -> None:
    """移除压缩目标比例字段。"""

    if not _has_column("ai_llm_configs", "compression_target_ratio"):
        return
    with op.batch_alter_table("ai_llm_configs") as batch_op:
        batch_op.drop_column("compression_target_ratio")
