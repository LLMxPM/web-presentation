"""文件功能：将基础字号与图标默认规格从主题迁移到项目页面配置。

Revision ID: 20260510_0048
Revises: 20260510_0047
Create Date: 2026-05-10 21:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
import yaml
from alembic import op


revision: str = "20260510_0048"
down_revision: str | None = "20260510_0047"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DEFAULT_BASE_FONT_SIZE = "16px"
DEFAULT_ICON_DEFAULT_SIZE = 20
DEFAULT_ICON_DEFAULT_STROKE_WIDTH = 2


def upgrade() -> None:
    """把页面视觉规格迁移到项目结构化字段。"""

    op.add_column(
        "projects",
        sa.Column("base_font_size", sa.String(length=32), nullable=False, server_default=sa.text(f"'{DEFAULT_BASE_FONT_SIZE}'")),
    )
    op.add_column(
        "projects",
        sa.Column("icon_default_size", sa.Integer(), nullable=False, server_default=sa.text(str(DEFAULT_ICON_DEFAULT_SIZE))),
    )
    op.add_column(
        "projects",
        sa.Column(
            "icon_default_stroke_width",
            sa.Integer(),
            nullable=False,
            server_default=sa.text(str(DEFAULT_ICON_DEFAULT_STROKE_WIDTH)),
        ),
    )

    _backfill_project_visual_specs()

    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.drop_column("icon_default_stroke_width")
        batch_op.drop_column("icon_default_size")
        batch_op.drop_column("base_font_size")


def downgrade() -> None:
    """恢复主题上的视觉规格字段，并移除项目字段。"""

    with op.batch_alter_table("workspace_themes") as batch_op:
        batch_op.add_column(sa.Column("base_font_size", sa.String(length=32), nullable=False, server_default=sa.text(f"'{DEFAULT_BASE_FONT_SIZE}'")))
        batch_op.add_column(sa.Column("icon_default_size", sa.Integer(), nullable=False, server_default=sa.text(str(DEFAULT_ICON_DEFAULT_SIZE))))
        batch_op.add_column(
            sa.Column(
                "icon_default_stroke_width",
                sa.Integer(),
                nullable=False,
                server_default=sa.text(str(DEFAULT_ICON_DEFAULT_STROKE_WIDTH)),
            )
        )

    _backfill_theme_visual_specs_from_projects()

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("icon_default_stroke_width")
        batch_op.drop_column("icon_default_size")
        batch_op.drop_column("base_font_size")


def _backfill_project_visual_specs() -> None:
    """按项目当前主题或 legacy YAML 回填项目视觉规格。"""

    bind = op.get_bind()
    themes = bind.execute(
        sa.text(
            """
            SELECT workspace_id, key, base_font_size, icon_default_size, icon_default_stroke_width
            FROM workspace_themes
            WHERE deleted_at IS NULL
            """
        )
    ).mappings()
    theme_map = {
        (int(item["workspace_id"]), str(item["key"] or "")): {
            "base_font_size": _normalize_base_font_size(item["base_font_size"]),
            "icon_default_size": _normalize_int(item["icon_default_size"], DEFAULT_ICON_DEFAULT_SIZE),
            "icon_default_stroke_width": _normalize_int(item["icon_default_stroke_width"], DEFAULT_ICON_DEFAULT_STROKE_WIDTH),
        }
        for item in themes
    }

    projects = bind.execute(
        sa.text(
            """
            SELECT id, workspace_id, theme_key, theme_config_yaml
            FROM projects
            WHERE deleted_at IS NULL
            """
        )
    ).mappings()
    for project in projects:
        specs = theme_map.get((int(project["workspace_id"]), str(project["theme_key"] or "")))
        if specs is None:
            specs = _extract_visual_specs_from_theme_yaml(str(project["theme_config_yaml"] or ""))
        bind.execute(
            sa.text(
                """
                UPDATE projects
                SET base_font_size = :base_font_size,
                    icon_default_size = :icon_default_size,
                    icon_default_stroke_width = :icon_default_stroke_width
                WHERE id = :project_id
                """
            ),
            {
                "project_id": project["id"],
                **specs,
            },
        )


def _backfill_theme_visual_specs_from_projects() -> None:
    """降级时用首个引用项目尽量恢复主题规格。"""

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT wt.id AS theme_id,
                   p.base_font_size AS base_font_size,
                   p.icon_default_size AS icon_default_size,
                   p.icon_default_stroke_width AS icon_default_stroke_width
            FROM workspace_themes wt
            JOIN projects p ON p.workspace_id = wt.workspace_id AND p.theme_key = wt.key
            WHERE wt.deleted_at IS NULL AND p.deleted_at IS NULL
            """
        )
    ).mappings()
    seen_theme_ids: set[int] = set()
    for row in rows:
        theme_id = int(row["theme_id"])
        if theme_id in seen_theme_ids:
            continue
        seen_theme_ids.add(theme_id)
        bind.execute(
            sa.text(
                """
                UPDATE workspace_themes
                SET base_font_size = :base_font_size,
                    icon_default_size = :icon_default_size,
                    icon_default_stroke_width = :icon_default_stroke_width
                WHERE id = :theme_id
                """
            ),
            {
                "theme_id": theme_id,
                "base_font_size": _normalize_base_font_size(row["base_font_size"]),
                "icon_default_size": _normalize_int(row["icon_default_size"], DEFAULT_ICON_DEFAULT_SIZE),
                "icon_default_stroke_width": _normalize_int(row["icon_default_stroke_width"], DEFAULT_ICON_DEFAULT_STROKE_WIDTH),
            },
        )


def _extract_visual_specs_from_theme_yaml(yaml_text: str) -> dict[str, object]:
    """从旧 themes.config.yaml 中提取默认主题规格。"""

    try:
        parsed = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        parsed = {}
    if not isinstance(parsed, dict):
        return _default_specs()

    themes = parsed.get("themes")
    if not isinstance(themes, dict) or not themes:
        return _default_specs()

    default_theme_key = ""
    default_section = parsed.get("default")
    if isinstance(default_section, dict):
        default_theme_key = str(default_section.get("theme") or "").strip()
    if not default_theme_key:
        default_theme_key = next(iter(themes.keys()), "")

    theme_entry = themes.get(default_theme_key)
    if not isinstance(theme_entry, dict):
        return _default_specs()

    typography = theme_entry.get("typography") if isinstance(theme_entry.get("typography"), dict) else {}
    icon = theme_entry.get("icon") if isinstance(theme_entry.get("icon"), dict) else {}
    return {
        "base_font_size": _normalize_base_font_size(typography.get("baseFontSize")),
        "icon_default_size": _normalize_int(icon.get("default_size"), DEFAULT_ICON_DEFAULT_SIZE),
        "icon_default_stroke_width": _normalize_int(icon.get("default_stroke_width"), DEFAULT_ICON_DEFAULT_STROKE_WIDTH),
    }


def _default_specs() -> dict[str, object]:
    """返回项目视觉规格默认值。"""

    return {
        "base_font_size": DEFAULT_BASE_FONT_SIZE,
        "icon_default_size": DEFAULT_ICON_DEFAULT_SIZE,
        "icon_default_stroke_width": DEFAULT_ICON_DEFAULT_STROKE_WIDTH,
    }


def _normalize_base_font_size(value: Any) -> str:
    """把字号归一为合法 px 字符串。"""

    normalized = str(value or "").strip().lower()
    if normalized.endswith("px"):
        normalized = normalized[:-2].strip()
    if not normalized.isdigit():
        return DEFAULT_BASE_FONT_SIZE
    numeric_value = int(normalized)
    if numeric_value < 1 or numeric_value > 200:
        return DEFAULT_BASE_FONT_SIZE
    return f"{numeric_value}px"


def _normalize_int(value: Any, default: int) -> int:
    """把规格数字归一为正整数。"""

    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return default
    return numeric_value if numeric_value > 0 else default
