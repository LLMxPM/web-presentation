"""add structured asset analysis metadata

Revision ID: 20260417_0022
Revises: 20260417_0021
Create Date: 2026-04-17 23:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260417_0022"
down_revision: Union[str, Sequence[str], None] = "20260417_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.add_column(sa.Column("analysis_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("workspace_assets") as batch_op:
        batch_op.drop_column("analysis_metadata")
