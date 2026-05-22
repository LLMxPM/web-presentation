"""文件功能：调整演示页默认字号与默认样式规范。

Revision ID: 20260519_0056
Revises: 20260516_0055
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260519_0056"
down_revision: str | None = "20260516_0055"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DEFAULT_STYLE_SPEC_MARKDOWN = """## 演示页排版尺度

- 本项目是固定 16:9 演示页/PPT 画布，不是普通网页桌面页。
- 页面应按投屏和远距离阅读设计，避免用网页信息流方式堆内容。
- 主标题优先使用 text-5xl 到 text-7xl。
- 章节标题、模块标题优先使用 text-3xl 到 text-5xl。
- 主体阅读文本优先使用 text-xl 到 text-3xl，不使用 text-sm、text-base 承载主要内容。
- text-xs、text-sm、text-base 只用于页脚、标签、角标、图例、注释或少量辅助信息。
- 单页只表达一个核心结论；内容过多时优先拆页，而不是缩小字号。
- 表格和指标区块应减少列数和行数，优先突出关键数字与结论。"""


def _has_table(table_name: str) -> bool:
    """检查数据库中是否已有目标表，兼容测试库和重复执行。"""

    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查表中是否已有目标列。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """将新建项目和样式的默认字号调整为演示页阅读尺度。"""

    if _has_table("projects") and _has_column("projects", "base_font_size"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.alter_column(
                "base_font_size",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'20px'"),
            )

    if _has_table("workspace_styles") and _has_column("workspace_styles", "base_font_size"):
        with op.batch_alter_table("workspace_styles") as batch_op:
            batch_op.alter_column(
                "base_font_size",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'20px'"),
            )

    if _has_table("workspace_styles") and _has_column("workspace_styles", "style_spec_markdown"):
        op.get_bind().execute(
            sa.text(
                """
                UPDATE workspace_styles
                SET base_font_size = '20px',
                    style_spec_markdown = :style_spec_markdown
                WHERE key = 'default'
                  AND base_font_size = '16px'
                  AND COALESCE(style_spec_markdown, '') = ''
                  AND deleted_at IS NULL
                """
            ),
            {"style_spec_markdown": DEFAULT_STYLE_SPEC_MARKDOWN},
        )


def downgrade() -> None:
    """恢复旧默认字号，并撤回仍保持新出厂文本的默认样式。"""

    if _has_table("workspace_styles") and _has_column("workspace_styles", "style_spec_markdown"):
        op.get_bind().execute(
            sa.text(
                """
                UPDATE workspace_styles
                SET base_font_size = '16px',
                    style_spec_markdown = ''
                WHERE key = 'default'
                  AND base_font_size = '20px'
                  AND style_spec_markdown = :style_spec_markdown
                  AND deleted_at IS NULL
                """
            ),
            {"style_spec_markdown": DEFAULT_STYLE_SPEC_MARKDOWN},
        )

    if _has_table("workspace_styles") and _has_column("workspace_styles", "base_font_size"):
        with op.batch_alter_table("workspace_styles") as batch_op:
            batch_op.alter_column(
                "base_font_size",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'16px'"),
            )

    if _has_table("projects") and _has_column("projects", "base_font_size"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.alter_column(
                "base_font_size",
                existing_type=sa.String(length=32),
                existing_nullable=False,
                server_default=sa.text("'16px'"),
            )
