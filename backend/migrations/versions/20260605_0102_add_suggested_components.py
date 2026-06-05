"""文件功能：新增样式与项目建议组件关联表。

Revision ID: 20260605_0102
Revises: 20260529_0101
Create Date: 2026-06-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260605_0102"
down_revision: Union[str, Sequence[str], None] = "20260529_0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建样式建议组件和项目建议组件快照关联表。"""

    op.create_table(
        "workspace_style_suggested_components",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("style_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["component_id"], ["workspace_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["style_id"], ["workspace_styles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("style_id", "component_id", name="uq_workspace_style_suggested_components_style_component"),
    )
    op.create_index(
        op.f("ix_workspace_style_suggested_components_component_id"),
        "workspace_style_suggested_components",
        ["component_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_style_suggested_components_style_id"),
        "workspace_style_suggested_components",
        ["style_id"],
        unique=False,
    )

    op.create_table(
        "project_suggested_components",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["component_id"], ["workspace_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "component_id", name="uq_project_suggested_components_project_component"),
    )
    op.create_index(
        op.f("ix_project_suggested_components_component_id"),
        "project_suggested_components",
        ["component_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_suggested_components_project_id"),
        "project_suggested_components",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """删除样式建议组件和项目建议组件快照关联表。"""

    op.drop_index(op.f("ix_project_suggested_components_project_id"), table_name="project_suggested_components")
    op.drop_index(op.f("ix_project_suggested_components_component_id"), table_name="project_suggested_components")
    op.drop_table("project_suggested_components")
    op.drop_index(
        op.f("ix_workspace_style_suggested_components_style_id"),
        table_name="workspace_style_suggested_components",
    )
    op.drop_index(
        op.f("ix_workspace_style_suggested_components_component_id"),
        table_name="workspace_style_suggested_components",
    )
    op.drop_table("workspace_style_suggested_components")
