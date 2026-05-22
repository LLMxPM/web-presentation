"""文件功能：将 pages 表中的 page_code 列重命名为 page_content，避免与业务编码字段 code 混淆。

Revision ID: 20260412_0012
Revises: 20260411_0011
Create Date: 2026-04-12 10:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260412_0012"
down_revision: str | None = "20260411_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """将 pages.page_code 重命名为 pages.page_content。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.alter_column(
            "page_code",
            new_column_name="page_content",
            existing_type=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    """回滚：将 pages.page_content 重命名回 pages.page_code。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.alter_column(
            "page_content",
            new_column_name="page_code",
            existing_type=sa.Text(),
            existing_nullable=False,
        )
