"""文件功能：调整用户级大模型配置的默认上下文窗口和默认输出 token。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260509_0043"
down_revision: str | None = "20260508_0042"
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
    """把新模型配置的数据库默认值调整为 128k 上下文和 32k 输出。"""

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        if _has_column("ai_llm_configs", "context_window_tokens"):
            batch_op.alter_column(
                "context_window_tokens",
                existing_type=sa.Integer(),
                existing_nullable=False,
                server_default=sa.text("128000"),
            )
        if _has_column("ai_llm_configs", "max_output_tokens"):
            batch_op.alter_column(
                "max_output_tokens",
                existing_type=sa.Integer(),
                existing_nullable=False,
                server_default=sa.text("32000"),
            )


def downgrade() -> None:
    """恢复旧数据库默认值。"""

    with op.batch_alter_table("ai_llm_configs") as batch_op:
        if _has_column("ai_llm_configs", "context_window_tokens"):
            batch_op.alter_column(
                "context_window_tokens",
                existing_type=sa.Integer(),
                existing_nullable=False,
                server_default=sa.text("32768"),
            )
        if _has_column("ai_llm_configs", "max_output_tokens"):
            batch_op.alter_column(
                "max_output_tokens",
                existing_type=sa.Integer(),
                existing_nullable=False,
                server_default=sa.text("4096"),
            )
