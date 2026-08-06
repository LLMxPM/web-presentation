"""文件功能：恢复工作空间默认样式并固化其默认主题引用。

Revision ID: 20260807_0100
Revises: 20260806_0200
Create Date: 2026-08-07 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260807_0100"
down_revision: Union[str, Sequence[str], None] = "20260806_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """重新启用 default 样式，并为其缺失主题补入工作空间默认主题。"""

    op.execute(
        """
        UPDATE workspace_styles
        SET deleted_at = NULL,
            theme_key = COALESCE(
                theme_key,
                (SELECT workspaces.default_theme_key FROM workspaces WHERE workspaces.id = workspace_styles.workspace_id)
            )
        WHERE key = 'default'
        """
    )


def downgrade() -> None:
    """数据修正不可安全逆转，降级时保留修正后的默认样式。"""

