"""重构工作空间资源类型与渲染元数据。

Revision ID: 20260427_0034
Revises: 20260426_0033
Create Date: 2026-04-27 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260427_0034"
down_revision: str | None = "20260426_0033"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增资源内容类型和渲染元数据字段，并移除旧插图类型。"""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.add_column(sa.Column("content_type", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("render_metadata", sa.JSON(), nullable=True))

    connection = op.get_bind()
    workspace_assets = sa.table(
        "workspace_assets",
        sa.column("asset_type", sa.String(length=50)),
    )
    connection.execute(
        workspace_assets.update()
        .where(workspace_assets.c.asset_type == "illustration")
        .values(asset_type="image")
    )


def downgrade() -> None:
    """移除资源内容类型和渲染元数据字段。"""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.drop_column("render_metadata")
        batch_op.drop_column("content_type")
