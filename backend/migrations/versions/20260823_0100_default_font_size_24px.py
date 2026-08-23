"""文件功能：将项目与工作空间样式的数据库默认基础字号调整为 24px。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260823_0100"
down_revision: Union[str, Sequence[str], None] = "20260822_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """将新建项目和工作空间样式的数据库默认字号改为 24px。"""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column(
            "base_font_size",
            existing_type=sa.String(length=32),
            server_default=sa.text("'24px'"),
        )
    with op.batch_alter_table("workspace_styles") as batch_op:
        batch_op.alter_column(
            "base_font_size",
            existing_type=sa.String(length=32),
            server_default=sa.text("'24px'"),
        )


def downgrade() -> None:
    """恢复项目和工作空间样式的数据库默认字号为 20px。"""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column(
            "base_font_size",
            existing_type=sa.String(length=32),
            server_default=sa.text("'20px'"),
        )
    with op.batch_alter_table("workspace_styles") as batch_op:
        batch_op.alter_column(
            "base_font_size",
            existing_type=sa.String(length=32),
            server_default=sa.text("'20px'"),
        )
