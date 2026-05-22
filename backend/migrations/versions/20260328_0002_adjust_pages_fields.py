"""文件功能：调整 pages 表结构，移除 name、slug、description 列，新增 page_code 列。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260328_0002"
down_revision: str | None = "20260328_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """移除 pages 表的 name、slug、description 字段，新增 page_code 字段。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(sa.Column("page_code", sa.String(length=128), nullable=False, server_default=""))
        batch_op.drop_column("name")
        batch_op.drop_column("slug")
        batch_op.drop_column("description")


def downgrade() -> None:
    """回滚：恢复 name、slug、description 字段，移除 page_code 字段。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("slug", sa.String(length=128), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("name", sa.String(length=128), nullable=False, server_default=""))
        batch_op.drop_column("page_code")
        batch_op.create_unique_constraint("uq_pages_slug", ["slug"])
