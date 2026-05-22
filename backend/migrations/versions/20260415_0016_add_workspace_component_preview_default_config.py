"""add workspace component preview default config

Revision ID: 20260415_0016
Revises: 20260412_0015
Create Date: 2026-04-15 16:00:00.000000

"""

from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260415_0016"
down_revision: Union[str, Sequence[str], None] = "20260412_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_COMPONENT_PREVIEW_CONFIG = {
    "release": {
        "page_width": 1920,
        "page_height": 1080,
        "theme_key": None,
        "theme_config_yaml": None,
    },
    "canvas": {
        "width": 960,
        "height": 540,
        "background": "#ffffff",
    },
}


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.add_column(sa.Column("component_preview_default_config", sa.JSON(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE workspaces
            SET component_preview_default_config = :component_preview_default_config
            WHERE component_preview_default_config IS NULL
            """
        ).bindparams(
            sa.bindparam(
                "component_preview_default_config",
                value=DEFAULT_COMPONENT_PREVIEW_CONFIG,
                type_=sa.JSON(),
            ),
        )
    )

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.alter_column("component_preview_default_config", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("workspaces") as batch_op:
        batch_op.drop_column("component_preview_default_config")
