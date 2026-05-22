"""文件功能：为页面截图补充生成时对应的页面版本号。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260425_0030"
down_revision = "20260419_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增截图版本号字段，历史截图保留空值表示未标记。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(sa.Column("screenshot_version_no", sa.Integer(), nullable=True))


def downgrade() -> None:
    """移除截图版本号字段。"""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.drop_column("screenshot_version_no")
