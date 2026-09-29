"""文件功能：删除页面变更 Batch 上未使用的 lease_generation 死列。

Revision ID: 20260930_0100
Revises: 20260929_0100
Create Date: 2026-09-30 01:00:00.000000

该列在统一任务运行时后已无读写方（页面 Batch 围栏改走领域 Job / ExternalBatch），
仅保留历史 schema。删除可消除 P2-VocabDrift 中的死列残留。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_0100"
down_revision: Union[str, Sequence[str], None] = "20260929_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """移除 ai_page_mutation_batches.lease_generation。"""

    op.drop_column("ai_page_mutation_batches", "lease_generation")


def downgrade() -> None:
    """恢复 lease_generation 列，默认 0。"""

    op.add_column(
        "ai_page_mutation_batches",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
    )
