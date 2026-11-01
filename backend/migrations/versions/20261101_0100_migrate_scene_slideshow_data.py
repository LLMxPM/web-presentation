"""文件功能：强制将已有项目与路由放映配置迁移到 schema 4，移除旧字段并保留可沿用设置。

Revision ID: 20261101_0100
Revises: 20261030_0100
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20261101_0100"
down_revision = "20261030_0100"
branch_labels = None
depends_on = None


def _integer(value: object, *, minimum: int, maximum: int, default: int) -> int:
    """仅保留 schema 4 范围内的整数，布尔和异常历史值恢复迁移时的固定默认。"""
    return value if type(value) is int and minimum <= value <= maximum else default


def _transition(value: object) -> dict:
    """保留合法翻页效果和时长；无效配置使用固定默认，不依赖未来应用 Schema。"""
    source = value if isinstance(value, dict) else {}
    effect = source.get("effect")
    if effect not in ("none", "fade", "push"):
        effect = "fade"
    duration = 0 if effect == "none" else _integer(source.get("duration_ms"), minimum=100, maximum=2000, default=400)
    return {"effect": effect, "duration_ms": duration}


def _advance(value: object) -> dict:
    """保留现行模式；已删除及未知模式统一改为手动，旧超时字段不再保存。"""
    source = value if isinstance(value, dict) else {}
    mode = source.get("mode")
    if mode not in ("manual", "timer", "scene_end"):
        mode = "manual"
    return {
        "mode": mode,
        "delay_ms": _integer(source.get("delay_ms"), minimum=1000, maximum=3600000, default=5000),
        "completion_delay_ms": _integer(source.get("completion_delay_ms"), minimum=0, maximum=3600000, default=300),
    }


def _project_settings(value: object) -> dict:
    """按固定 schema 4 字段重建完整配置，剔除 auto_start 等全部旧字段。"""
    source = value if isinstance(value, dict) else {}
    loop = source.get("loop")
    return {
        "transition": _transition(source.get("transition")),
        "advance": _advance(source.get("advance")),
        "loop": loop if isinstance(loop, bool) else False,
    }


def _changed(original: object, normalized: object) -> bool:
    """比较 JSON 表达，区分 Python 判等相同的整数、浮点和布尔，确保严格类型也被修复。"""
    return json.dumps(original, sort_keys=True) != json.dumps(normalized, sort_keys=True)


def upgrade() -> None:
    """在迁移事务内逐行更新小规模配置；保留路由继承，分组清空不应存在的覆盖。"""
    connection = op.get_bind()
    projects = sa.table("projects", sa.column("id", sa.Integer()), sa.column("slideshow_config_json", sa.JSON()))
    routes = sa.table(
        "project_routes", sa.column("id", sa.Integer()), sa.column("route_type", sa.String()),
        sa.column("transition_json", sa.JSON()), sa.column("advance_json", sa.JSON()),
    )
    for row in connection.execute(sa.select(projects)).mappings().all():
        normalized = _project_settings(row["slideshow_config_json"])
        if _changed(row["slideshow_config_json"], normalized):
            connection.execute(projects.update().where(projects.c.id == row["id"]).values(slideshow_config_json=normalized))
    for row in connection.execute(sa.select(routes)).mappings().all():
        is_page = row["route_type"] == "page"
        transition = _transition(row["transition_json"]) if is_page and row["transition_json"] is not None else None
        advance = _advance(row["advance_json"]) if is_page and row["advance_json"] is not None else None
        if _changed(row["transition_json"], transition) or _changed(row["advance_json"], advance):
            connection.execute(routes.update().where(routes.c.id == row["id"]).values(transition_json=transition, advance_json=advance))


def downgrade() -> None:
    """数据转换不回译：已删除模式和字段无法无损恢复，降级应用前应还原数据库备份。"""
