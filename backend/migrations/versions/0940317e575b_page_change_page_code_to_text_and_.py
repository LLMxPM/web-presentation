"""Page: change page_code to Text and update schemas

Revision ID: 0940317e575b
Revises: ff248165ae88
Create Date: 2026-03-28 16:12:13.464749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0940317e575b'
down_revision: Union[str, Sequence[str], None] = 'ff248165ae88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('pages') as batch_op:
        batch_op.alter_column(
            'page_code',
            existing_type=sa.VARCHAR(length=128),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pages') as batch_op:
        batch_op.alter_column(
            'page_code',
            existing_type=sa.Text(),
            type_=sa.VARCHAR(length=128),
            existing_nullable=False,
        )
