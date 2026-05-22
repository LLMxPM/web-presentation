"""文件功能：移除独立默认图标尺寸配置，图标尺寸改由基础字号和 Tailwind 类控制。

Revision ID: 20260522_0058
Revises: 20260519_0057
Create Date: 2026-05-22 00:00:00.000000
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260522_0058"
down_revision: str | None = "20260519_0057"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    """创建结构检查器，避免迁移重复执行时误判。"""

    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    """检查表是否存在。"""

    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查字段是否存在。"""

    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    """存在目标字段时删除。"""

    if not _has_column(table_name, column_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column(column_name)


def _add_icon_default_size_if_missing(table_name: str) -> None:
    """降级时恢复旧字段，数据统一回填默认值。"""

    if not _has_table(table_name) or _has_column(table_name, "icon_default_size"):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(
            sa.Column("icon_default_size", sa.Integer(), nullable=False, server_default=sa.text("20"))
        )


def _clean_user_preview_size_presets() -> None:
    """移除用户预设尺寸 JSON 中的 icon_default_size 字段。"""

    if not _has_column("users", "preview_size_presets"):
        return

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, preview_size_presets FROM users")).mappings()
    for row in rows:
        presets = row["preview_size_presets"]
        if isinstance(presets, str):
            try:
                presets = json.loads(presets)
            except json.JSONDecodeError:
                continue
        if not isinstance(presets, list):
            continue
        cleaned_presets = []
        changed = False
        for preset in presets:
            if not isinstance(preset, dict):
                cleaned_presets.append(preset)
                continue
            cleaned_preset = dict(preset)
            if "icon_default_size" in cleaned_preset:
                cleaned_preset.pop("icon_default_size", None)
                changed = True
            cleaned_presets.append(cleaned_preset)
        if changed:
            connection.execute(
                sa.text("UPDATE users SET preview_size_presets = :presets WHERE id = :user_id").bindparams(
                    sa.bindparam("presets", type_=sa.JSON())
                ),
                {"presets": cleaned_presets, "user_id": row["id"]},
            )


def upgrade() -> None:
    """删除默认图标尺寸字段，并清理用户预设尺寸 JSON。"""

    _clean_user_preview_size_presets()
    _drop_column_if_exists("projects", "icon_default_size")
    _drop_column_if_exists("workspace_styles", "icon_default_size")


def downgrade() -> None:
    """恢复旧字段；用户预设尺寸 JSON 不做反向补齐。"""

    _add_icon_default_size_if_missing("projects")
    _add_icon_default_size_if_missing("workspace_styles")
