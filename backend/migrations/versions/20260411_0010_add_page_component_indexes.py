"""文件功能：新增页面版本组件索引表，记录组件集合与 Icon/Asset name 参数集合。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260411_0010"
down_revision: str | None = "d8604be26ae5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """创建页面版本组件索引相关表和索引。"""

    op.create_table(
        "page_version_component_usages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_version_id", sa.Integer(), sa.ForeignKey("page_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "page_version_id",
            "component_name",
            name="uq_page_version_component_usages_version_component",
        ),
    )
    op.create_index(
        "ix_page_version_component_usages_project_id",
        "page_version_component_usages",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_version_component_usages_page_id",
        "page_version_component_usages",
        ["page_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_version_component_usages_page_version_id",
        "page_version_component_usages",
        ["page_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_version_component_usages_project_component",
        "page_version_component_usages",
        ["project_id", "component_name"],
        unique=False,
    )

    op.create_table(
        "page_version_component_resources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_version_id", sa.Integer(), sa.ForeignKey("page_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_name", sa.String(length=128), nullable=False),
        sa.Column("resource_attr", sa.String(length=64), nullable=False, server_default="name"),
        sa.Column("resource_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "page_version_id",
            "component_name",
            "resource_attr",
            "resource_name",
            name="uq_page_version_component_resources_unique_resource",
        ),
    )
    op.create_index(
        "ix_page_version_component_resources_project_id",
        "page_version_component_resources",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_version_component_resources_page_id",
        "page_version_component_resources",
        ["page_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_version_component_resources_page_version_id",
        "page_version_component_resources",
        ["page_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_page_version_component_resources_project_component_resource",
        "page_version_component_resources",
        ["project_id", "component_name", "resource_name"],
        unique=False,
    )


def downgrade() -> None:
    """回滚页面版本组件索引表和索引。"""

    op.drop_index("ix_page_version_component_resources_project_component_resource", table_name="page_version_component_resources")
    op.drop_index("ix_page_version_component_resources_page_version_id", table_name="page_version_component_resources")
    op.drop_index("ix_page_version_component_resources_page_id", table_name="page_version_component_resources")
    op.drop_index("ix_page_version_component_resources_project_id", table_name="page_version_component_resources")
    op.drop_table("page_version_component_resources")

    op.drop_index("ix_page_version_component_usages_project_component", table_name="page_version_component_usages")
    op.drop_index("ix_page_version_component_usages_page_version_id", table_name="page_version_component_usages")
    op.drop_index("ix_page_version_component_usages_page_id", table_name="page_version_component_usages")
    op.drop_index("ix_page_version_component_usages_project_id", table_name="page_version_component_usages")
    op.drop_table("page_version_component_usages")
