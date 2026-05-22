"""replace project route yaml with structured table

Revision ID: 20260417_0018
Revises: 20260416_0017
Create Date: 2026-04-17 15:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260417_0018"
down_revision: Union[str, Sequence[str], None] = "20260416_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "project_routes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("route", sa.String(length=128), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(length=128), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("route_type", sa.String(length=32), nullable=False),
        sa.Column("group_title", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["project_routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_routes_project_id"), "project_routes", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_routes_parent_id"), "project_routes", ["parent_id"], unique=False)
    op.create_index(op.f("ix_project_routes_page_id"), "project_routes", ["page_id"], unique=False)

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("route_config_yaml")


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("route_config_yaml", sa.Text(), nullable=False, server_default="routes: []\n"))

    op.drop_index(op.f("ix_project_routes_page_id"), table_name="project_routes")
    op.drop_index(op.f("ix_project_routes_parent_id"), table_name="project_routes")
    op.drop_index(op.f("ix_project_routes_project_id"), table_name="project_routes")
    op.drop_table("project_routes")
