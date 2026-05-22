"""文件功能：为工作空间组件新增源码默认导入引用名。

Revision ID: 20260509_0046
Revises: 20260509_0045
Create Date: 2026-05-09 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260509_0046"
down_revision: str | None = "20260509_0045"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增组件引用名字段，并用历史组件编码回填。"""

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.add_column(sa.Column("import_name", sa.String(length=64), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE workspace_components SET import_name = code WHERE import_name IS NULL OR import_name = ''")
    )

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.alter_column("import_name", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index(
            "ix_workspace_components_workspace_import_name_status",
            ["workspace_id", "import_name", "status"],
            unique=False,
        )


def downgrade() -> None:
    """移除组件引用名字段。"""

    with op.batch_alter_table("workspace_components") as batch_op:
        batch_op.drop_index("ix_workspace_components_workspace_import_name_status")
        batch_op.drop_column("import_name")
