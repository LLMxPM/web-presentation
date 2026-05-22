"""structure project app config fields

Revision ID: 20260417_0019
Revises: 20260417_0018
Create Date: 2026-04-17 18:20:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260417_0019"
down_revision: Union[str, Sequence[str], None] = "20260417_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("icon", sa.String(length=128), nullable=False, server_default=sa.text("'slider'")))
        batch_op.add_column(sa.Column("page_width", sa.Integer(), nullable=False, server_default=sa.text("1920")))
        batch_op.add_column(sa.Column("page_height", sa.Integer(), nullable=False, server_default=sa.text("1080")))
        batch_op.add_column(sa.Column("show_pdf_export_button", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        batch_op.add_column(sa.Column("menu_mode", sa.String(length=16), nullable=False, server_default=sa.text("'preview'")))
        batch_op.drop_column("app_config_yaml")


def downgrade() -> None:
    """Downgrade schema."""

    default_app_config_yaml = """app:
  icon: slider
  title: ''
  description: ''
  page:
    width: 1920
    height: 1080
  features:
    showPdfExportButton: true
    menuMode: preview
"""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("app_config_yaml", sa.Text(), nullable=False, server_default=default_app_config_yaml))
        batch_op.drop_column("menu_mode")
        batch_op.drop_column("show_pdf_export_button")
        batch_op.drop_column("page_height")
        batch_op.drop_column("page_width")
        batch_op.drop_column("icon")
