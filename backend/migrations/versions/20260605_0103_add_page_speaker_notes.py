"""文件功能：为页面与页面版本增加演讲者备注字段。

Revision ID: 20260605_0103
Revises: 20260605_0102
Create Date: 2026-06-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260605_0103"
down_revision: Union[str, Sequence[str], None] = "20260605_0102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加页面当前备注与版本备注快照列。"""

    op.add_column("pages", sa.Column("speaker_notes", sa.Text(), nullable=True))
    op.add_column("page_versions", sa.Column("speaker_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    """移除页面当前备注与版本备注快照列。"""

    op.drop_column("page_versions", "speaker_notes")
    op.drop_column("pages", "speaker_notes")
