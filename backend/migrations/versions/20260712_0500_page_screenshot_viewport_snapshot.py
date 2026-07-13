"""文件功能：记录页面公开截图指针对应的视口，避免跨尺寸缓存误命中。

Revision ID: 20260712_0500
Revises: 20260712_0400
Create Date: 2026-07-12 05:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260712_0500"
down_revision: Union[str, Sequence[str], None] = "20260712_0400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为既有页面截图指针增加可空视口元数据；旧截图会在下次刷新时补齐。"""

    op.add_column("pages", sa.Column("screenshot_viewport_width", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("screenshot_viewport_height", sa.Integer(), nullable=True))


def downgrade() -> None:
    """移除公开截图视口元数据。"""

    op.drop_column("pages", "screenshot_viewport_height")
    op.drop_column("pages", "screenshot_viewport_width")
