"""文件功能：为工作空间组件补充可检索的组件类型字段。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260419_0029"
down_revision = "20260419_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 component_type 字段并为历史数据回填默认值。"""

    op.add_column(
        "workspace_components",
        sa.Column("component_type", sa.String(length=64), nullable=False, server_default="general"),
    )
    op.create_index(
        "ix_workspace_components_component_type",
        "workspace_components",
        ["component_type"],
        unique=False,
    )
    op.execute("UPDATE workspace_components SET component_type = 'general' WHERE component_type IS NULL OR component_type = ''")


def downgrade() -> None:
    """移除 component_type 字段及其索引。"""

    op.drop_index("ix_workspace_components_component_type", table_name="workspace_components")
    op.drop_column("workspace_components", "component_type")
