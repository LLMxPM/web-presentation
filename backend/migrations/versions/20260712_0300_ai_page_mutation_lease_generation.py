"""文件功能：为 AI 页面变更批次增加续跑租约代次，提供跨实例写入围栏。

Revision ID: 20260712_0300
Revises: 20260712_0200
Create Date: 2026-07-12 03:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_0300"
down_revision: Union[str, Sequence[str], None] = "20260712_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为已有 Batch 回填零代次，后续每次认领都用条件更新递增。"""

    op.add_column(
        "ai_page_mutation_batches",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    """移除续跑租约代次字段。"""

    op.drop_column("ai_page_mutation_batches", "lease_generation")
