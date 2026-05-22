"""add page screenshot storage fields

Revision ID: 20260402_0008
Revises: 20260331_0007
Create Date: 2026-04-02 10:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260402_0008"
down_revision: Union[str, Sequence[str], None] = "20260331_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.add_column(sa.Column("screenshot_storage_key", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("screenshot_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("pages") as batch_op:
        batch_op.drop_column("screenshot_updated_at")
        batch_op.drop_column("screenshot_storage_key")
