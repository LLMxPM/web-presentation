"""add project archived_at timestamp

Revision ID: 20260417_0023
Revises: 20260417_0022
Create Date: 2026-04-17 23:55:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260417_0023"
down_revision: Union[str, Sequence[str], None] = "20260417_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE projects
            SET archived_at = updated_at
            WHERE status = 'archived' AND archived_at IS NULL
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("archived_at")
