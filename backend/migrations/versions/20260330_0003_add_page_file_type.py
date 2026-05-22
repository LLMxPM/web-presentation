"""文件功能：为 pages 表新增 file_type 字段，并为存量数据回填默认扩展名。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_0003"
down_revision: str | None = "0940317e575b"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增 page 文件类型字段，并统一为旧数据回填 vue。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(sa.Column("file_type", sa.String(length=32), nullable=False, server_default="vue"))


def downgrade() -> None:
    """回滚 pages 表中的 file_type 字段。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.drop_column("file_type")
