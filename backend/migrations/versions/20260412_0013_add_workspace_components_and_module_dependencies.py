"""add workspace component tables and module dependency indexes

Revision ID: 20260412_0013
Revises: 20260412_0012
Create Date: 2026-04-12 10:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260412_0013"
down_revision = "20260412_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_components",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("current_version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workspace_components_workspace_id", "workspace_components", ["workspace_id"], unique=False)

    op.create_table(
        "workspace_component_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("component_id", sa.Integer(), sa.ForeignKey("workspace_components.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("change_note", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("component_id", "version_no", name="uq_workspace_component_versions_component_version"),
    )
    op.create_index("ix_workspace_component_versions_component_id", "workspace_component_versions", ["component_id"], unique=False)

    op.create_table(
        "page_version_component_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_version_id", sa.Integer(), sa.ForeignKey("page_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependency_kind", sa.String(length=32), nullable=False),
        sa.Column("component_id", sa.Integer(), sa.ForeignKey("workspace_components.id", ondelete="CASCADE"), nullable=True),
        sa.Column("component_version_id", sa.Integer(), sa.ForeignKey("workspace_component_versions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("component_code", sa.String(length=64), nullable=True),
        sa.Column("component_version_no", sa.Integer(), nullable=True),
        sa.Column("runtime_module_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "page_version_id",
            "dependency_kind",
            "component_version_id",
            "runtime_module_path",
            name="uq_page_version_component_dependencies_unique_dependency",
        ),
    )
    op.create_index("ix_pvcd_page_id", "page_version_component_dependencies", ["page_id"], unique=False)
    op.create_index("ix_pvcd_pver_id", "page_version_component_dependencies", ["page_version_id"], unique=False)
    op.create_index("ix_pvcd_comp_id", "page_version_component_dependencies", ["component_id"], unique=False)
    op.create_index("ix_pvcd_cver_id", "page_version_component_dependencies", ["component_version_id"], unique=False)

    op.create_table(
        "component_version_component_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("component_id", sa.Integer(), sa.ForeignKey("workspace_components.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_version_id", sa.Integer(), sa.ForeignKey("workspace_component_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependency_kind", sa.String(length=32), nullable=False),
        sa.Column("dependency_component_id", sa.Integer(), sa.ForeignKey("workspace_components.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dependency_component_version_id", sa.Integer(), sa.ForeignKey("workspace_component_versions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dependency_component_code", sa.String(length=64), nullable=True),
        sa.Column("dependency_component_version_no", sa.Integer(), nullable=True),
        sa.Column("runtime_module_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "component_version_id",
            "dependency_kind",
            "dependency_component_version_id",
            "runtime_module_path",
            name="uq_component_version_component_dependencies_unique_dependency",
        ),
    )
    op.create_index("ix_cvcd_comp_id", "component_version_component_dependencies", ["component_id"], unique=False)
    op.create_index("ix_cvcd_cver_id", "component_version_component_dependencies", ["component_version_id"], unique=False)
    op.create_index("ix_cvcd_dep_comp_id", "component_version_component_dependencies", ["dependency_component_id"], unique=False)
    op.create_index("ix_cvcd_dep_cver_id", "component_version_component_dependencies", ["dependency_component_version_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_cvcd_dep_cver_id", table_name="component_version_component_dependencies")
    op.drop_index("ix_cvcd_dep_comp_id", table_name="component_version_component_dependencies")
    op.drop_index("ix_cvcd_cver_id", table_name="component_version_component_dependencies")
    op.drop_index("ix_cvcd_comp_id", table_name="component_version_component_dependencies")
    op.drop_table("component_version_component_dependencies")

    op.drop_index("ix_pvcd_cver_id", table_name="page_version_component_dependencies")
    op.drop_index("ix_pvcd_comp_id", table_name="page_version_component_dependencies")
    op.drop_index("ix_pvcd_pver_id", table_name="page_version_component_dependencies")
    op.drop_index("ix_pvcd_page_id", table_name="page_version_component_dependencies")
    op.drop_table("page_version_component_dependencies")

    op.drop_index("ix_workspace_component_versions_component_id", table_name="workspace_component_versions")
    op.drop_table("workspace_component_versions")

    op.drop_index("ix_workspace_components_workspace_id", table_name="workspace_components")
    op.drop_table("workspace_components")
