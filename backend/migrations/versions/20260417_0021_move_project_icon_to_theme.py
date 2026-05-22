"""move project icon ownership from project to workspace theme

Revision ID: 20260417_0021
Revises: 20260417_0020
Create Date: 2026-04-17 22:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260417_0021"
down_revision: Union[str, Sequence[str], None] = "20260417_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.add_column(sa.Column("project_icon_asset_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("project_icon_name", sa.String(length=255), nullable=True, server_default="slider"))
        batch_op.create_index("ix_workspace_themes_project_icon_asset_id", ["project_icon_asset_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_workspace_themes_project_icon_asset_id_workspace_assets",
            "workspace_assets",
            ["project_icon_asset_id"],
            ["id"],
        )

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("icon")


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("icon", sa.String(length=128), nullable=False, server_default="slider"))

    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.drop_constraint("fk_workspace_themes_project_icon_asset_id_workspace_assets", type_="foreignkey")
        batch_op.drop_index("ix_workspace_themes_project_icon_asset_id")
        batch_op.drop_column("project_icon_name")
        batch_op.drop_column("project_icon_asset_id")
