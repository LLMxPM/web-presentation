"""文件功能：将工作空间组件类型默认值切换为精简后的内容组件。

Revision ID: 20260609_0106
Revises: 20260608_0105
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260609_0106"
down_revision: Union[str, Sequence[str], None] = "20260608_0105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """把组件类型列的数据库默认值改为内容组件。"""

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.alter_column(
            "component_type",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            server_default="内容组件",
        )


def downgrade() -> None:
    """回退组件类型列的数据库默认值。"""

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.alter_column(
            "component_type",
            existing_type=sa.String(length=64),
            existing_nullable=False,
            server_default="内容区块",
        )
