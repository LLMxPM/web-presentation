"""文件功能：新增组件发布版本资源参数索引表。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260513_0050"
down_revision: str | None = "20260511_0049"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """创建组件版本资源索引表和查询索引。"""

    op.create_table(
        "component_version_component_resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "component_id",
            sa.Integer(),
            sa.ForeignKey("workspace_components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "component_version_id",
            sa.Integer(),
            sa.ForeignKey("workspace_component_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("component_name", sa.String(length=128), nullable=False),
        sa.Column("resource_attr", sa.String(length=64), nullable=False, server_default="name"),
        sa.Column("resource_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "component_version_id",
            "component_name",
            "resource_attr",
            "resource_name",
            name="uq_component_version_component_resources_unique_resource",
        ),
    )
    op.create_index("ix_cvcr_workspace_id", "component_version_component_resources", ["workspace_id"], unique=False)
    op.create_index("ix_cvcr_component_id", "component_version_component_resources", ["component_id"], unique=False)
    op.create_index(
        "ix_cvcr_component_version_id",
        "component_version_component_resources",
        ["component_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_cvcr_workspace_component_resource",
        "component_version_component_resources",
        ["workspace_id", "component_name", "resource_name"],
        unique=False,
    )


def downgrade() -> None:
    """删除组件版本资源索引表。"""

    op.drop_index("ix_cvcr_workspace_component_resource", table_name="component_version_component_resources")
    op.drop_index("ix_cvcr_component_version_id", table_name="component_version_component_resources")
    op.drop_index("ix_cvcr_component_id", table_name="component_version_component_resources")
    op.drop_index("ix_cvcr_workspace_id", table_name="component_version_component_resources")
    op.drop_table("component_version_component_resources")
