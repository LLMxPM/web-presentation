"""文件功能：新增项目建议引用资源关联表。

Revision ID: 20260529_0101
Revises: 20260526_0100
Create Date: 2026-05-29 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260529_0101"
down_revision: Union[str, Sequence[str], None] = "20260526_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建项目建议引用内容资源关联表。"""

    op.create_table(
        "project_suggested_reference_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["workspace_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "asset_id", name="uq_project_suggested_reference_assets_project_asset"),
    )
    op.create_index(
        op.f("ix_project_suggested_reference_assets_asset_id"),
        "project_suggested_reference_assets",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_suggested_reference_assets_project_id"),
        "project_suggested_reference_assets",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """删除项目建议引用内容资源关联表。"""

    op.drop_index(
        op.f("ix_project_suggested_reference_assets_project_id"),
        table_name="project_suggested_reference_assets",
    )
    op.drop_index(
        op.f("ix_project_suggested_reference_assets_asset_id"),
        table_name="project_suggested_reference_assets",
    )
    op.drop_table("project_suggested_reference_assets")
