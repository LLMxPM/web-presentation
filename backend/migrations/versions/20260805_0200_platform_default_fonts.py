"""文件功能：把仍使用原始系统默认字体的内置主题迁移到跨端一致的平台字体。

Revision ID: 20260805_0200
Revises: 20260805_0100
Create Date: 2026-08-05 02:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260805_0200"
down_revision: Union[str, Sequence[str], None] = "20260805_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """只迁移未绑定字体资源且保持原始值的系统内置主题。"""

    op.execute(
        """
        UPDATE workspace_themes
        SET heading_font_label = 'platform-sans',
            body_font_label = 'platform-sans',
            code_font_label = 'platform-mono',
            updated_at = CURRENT_TIMESTAMP
        WHERE heading_font_family_id IS NULL
          AND body_font_family_id IS NULL
          AND code_font_family_id IS NULL
          AND heading_font_label = 'system-ui'
          AND body_font_label = 'system-ui'
          AND code_font_label = 'monospace'
        """
    )


def downgrade() -> None:
    """将本次迁移命中的平台默认主题恢复为旧系统字体 token。"""

    op.execute(
        """
        UPDATE workspace_themes
        SET heading_font_label = 'system-ui',
            body_font_label = 'system-ui',
            code_font_label = 'monospace',
            updated_at = CURRENT_TIMESTAMP
        WHERE heading_font_family_id IS NULL
          AND body_font_family_id IS NULL
          AND code_font_family_id IS NULL
          AND heading_font_label = 'platform-sans'
          AND body_font_label = 'platform-sans'
          AND code_font_label = 'platform-mono'
        """
    )
