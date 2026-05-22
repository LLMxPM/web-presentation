"""文件功能：新增工作空间样式库与项目样式规范字段。

Revision ID: 20260516_0055
Revises: 20260516_0054
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260516_0055"
down_revision: str | None = "20260516_0054"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    """检查数据库中是否已有目标表，兼容重复执行。"""

    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查表中是否已有目标列，兼容重复执行。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """新增样式库表并为已有工作空间补齐默认样式。"""

    if not _has_column("projects", "style_spec_markdown"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(sa.Column("style_spec_markdown", sa.Text(), nullable=False, server_default=sa.text("''")))

    if not _has_table("workspace_styles"):
        op.create_table(
            "workspace_styles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("page_width", sa.Integer(), nullable=False, server_default=sa.text("1920")),
            sa.Column("page_height", sa.Integer(), nullable=False, server_default=sa.text("1080")),
            sa.Column("base_font_size", sa.String(length=32), nullable=False, server_default=sa.text("'16px'")),
            sa.Column("icon_default_size", sa.Integer(), nullable=False, server_default=sa.text("20")),
            sa.Column("icon_default_stroke_width", sa.Integer(), nullable=False, server_default=sa.text("2")),
            sa.Column("show_pdf_export_button", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("menu_mode", sa.String(length=16), nullable=False, server_default=sa.text("'preview'")),
            sa.Column("theme_key", sa.String(length=64), nullable=True),
            sa.Column("style_spec_markdown", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("workspace_id", "key", name="uq_workspace_styles_workspace_key"),
        )
        op.create_index("ix_workspace_styles_workspace_id", "workspace_styles", ["workspace_id"])

    _backfill_default_workspace_styles()


def downgrade() -> None:
    """移除样式库表和项目样式规范字段。"""

    if _has_table("workspace_styles"):
        op.drop_index("ix_workspace_styles_workspace_id", table_name="workspace_styles")
        op.drop_table("workspace_styles")

    if _has_column("projects", "style_spec_markdown"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_column("style_spec_markdown")


def _backfill_default_workspace_styles() -> None:
    """为已有工作空间创建一个默认样式，避免迁移后样式库为空。"""

    bind = op.get_bind()
    workspaces = bind.execute(
        sa.text(
            """
            SELECT id, default_theme_key
            FROM workspaces
            WHERE deleted_at IS NULL
            """
        )
    ).mappings()
    for workspace in workspaces:
        existing_id = bind.execute(
            sa.text(
                """
                SELECT id
                FROM workspace_styles
                WHERE workspace_id = :workspace_id AND key = 'default'
                LIMIT 1
                """
            ),
            {"workspace_id": workspace["id"]},
        ).scalar()
        if existing_id is not None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO workspace_styles (
                    workspace_id, key, name, description,
                    page_width, page_height, base_font_size,
                    icon_default_size, icon_default_stroke_width,
                    show_pdf_export_button, menu_mode, theme_key, style_spec_markdown
                ) VALUES (
                    :workspace_id, 'default', '默认样式', '系统迁移生成的默认样式。',
                    1920, 1080, '16px',
                    20, 2,
                    true, 'preview', :theme_key, ''
                )
                """
            ),
            {
                "workspace_id": workspace["id"],
                "theme_key": workspace["default_theme_key"],
            },
        )
