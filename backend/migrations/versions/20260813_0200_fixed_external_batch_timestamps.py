"""文件功能：修复统一外部 Batch/Task 表时间戳列缺失服务端默认值的问题。

Revision ID: 20260813_0200
Revises: 20260813_0100
Create Date: 2026-08-13 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0200"
down_revision: Union[str, Sequence[str], None] = "20260813_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIMESTAMP_TABLES = ("ai_agent_external_batches", "ai_agent_external_tasks")


def upgrade() -> None:
    """为时间戳列补充服务端默认值，与模型 TimestampMixin 的 server_default 对齐。"""

    for table in _TIMESTAMP_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                nullable=False,
                server_default=sa.func.now(),
            )
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                nullable=False,
                server_default=sa.func.now(),
            )


def downgrade() -> None:
    """移除时间戳列服务端默认值，恢复 0100 迁移的原始表结构。"""

    for table in _TIMESTAMP_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                nullable=False,
                server_default=None,
            )
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                nullable=False,
                server_default=None,
            )
