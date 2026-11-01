"""文件功能：在真实 SQLite 事务验证放映数据强制迁移、路由继承和重复执行不改写合法配置。"""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.slideshow_defaults import default_slideshow_payload
from app.schemas.slideshow import (
    SlideshowAdvance,
    SlideshowSettings,
    SlideshowTransition,
)


@pytest.fixture
def migration_database():
    """创建仅包含配置列的临时库，独立加载迁移，不接触开发数据库。"""
    path = Path(__file__).resolve().parents[2] / "migrations/versions/20261101_0100_migrate_scene_slideshow_data.py"
    spec = importlib.util.spec_from_file_location("scene_slideshow_data_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata = sa.MetaData()
    projects = sa.Table("projects", metadata, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("slideshow_config_json", sa.JSON()))
    routes = sa.Table(
        "project_routes", metadata, sa.Column("id", sa.Integer(), primary_key=True), sa.Column("route_type", sa.String()),
        sa.Column("transition_json", sa.JSON()), sa.Column("advance_json", sa.JSON()),
    )
    engine = sa.create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            yield migration, connection, projects, routes
    finally:
        engine.dispose()


@pytest.mark.parametrize("mode", ["manual", "timer", "media_end", "timeline_end"])
def test_upgrade_legacy_project_and_route_configuration(migration_database, mode):
    """所有旧模式迁为严格现行 DTO；保留动画、循环、合法时长和路由的独立覆盖。"""
    migration, connection, projects, routes = migration_database
    old_advance = {"mode": mode, "delay_ms": 12000, "media_timeout_ms": 60000, "timeline_timeout_ms": 90000}
    transition = {"effect": "push", "duration_ms": 650}
    old_project = {"transition": transition, "advance": old_advance, "loop": True, "auto_start": True}
    connection.execute(projects.insert().values(id=1, slideshow_config_json=old_project))
    connection.execute(routes.insert(), [
        {"id": 1, "route_type": "page", "transition_json": None, "advance_json": None},
        {"id": 2, "route_type": "page", "transition_json": transition, "advance_json": old_advance},
        {"id": 3, "route_type": "group", "transition_json": transition, "advance_json": old_advance},
    ])

    migration.upgrade()

    migrated_project = connection.execute(sa.select(projects.c.slideshow_config_json)).scalar_one()
    settings = SlideshowSettings.model_validate(migrated_project)
    assert settings.transition.model_dump() == transition
    assert settings.loop is True
    assert settings.advance.mode == (mode if mode in {"manual", "timer"} else "manual")
    assert settings.advance.delay_ms == 12000
    assert settings.advance.completion_delay_ms == 300
    assert "auto_start" not in migrated_project
    rows = connection.execute(sa.select(routes).order_by(routes.c.id)).mappings().all()
    assert rows[0]["transition_json"] is None and rows[0]["advance_json"] is None
    assert SlideshowTransition.model_validate(rows[1]["transition_json"]).model_dump() == transition
    assert SlideshowAdvance.model_validate(rows[1]["advance_json"]) == settings.advance
    assert rows[2]["transition_json"] is None and rows[2]["advance_json"] is None


@pytest.mark.parametrize("value", [None, [], "bad", {}, {
    "transition": {"effect": "fade", "duration_ms": True},
    "advance": {"mode": "unknown", "delay_ms": "5000", "completion_delay_ms": -1}, "loop": 1,
}])
def test_upgrade_invalid_configuration_uses_fixed_defaults(migration_database, value):
    """异常历史值统一恢复完整默认配置，避免升级后项目读取仍因严格解析失败。"""
    migration, connection, projects, _ = migration_database
    connection.execute(projects.insert().values(id=1, slideshow_config_json=value))
    migration.upgrade()
    migrated = connection.execute(sa.select(projects.c.slideshow_config_json)).scalar_one()
    assert migrated == default_slideshow_payload()
    SlideshowSettings.model_validate(migrated)


def test_upgrade_keeps_current_scene_configuration_and_is_idempotent(migration_database):
    """现行 scene_end、零完成后停留和 none 效果不变，二次执行不再发出 UPDATE。"""
    migration, connection, projects, routes = migration_database
    current = {
        "transition": {"effect": "none", "duration_ms": 0},
        "advance": {"mode": "scene_end", "delay_ms": 1000, "completion_delay_ms": 0}, "loop": False,
    }
    connection.execute(projects.insert().values(id=1, slideshow_config_json=current))
    connection.execute(routes.insert().values(id=1, route_type="page", transition_json=current["transition"], advance_json=current["advance"]))
    updates = []

    @sa.event.listens_for(connection, "before_cursor_execute")
    def collect_updates(conn, cursor, statement, parameters, context, executemany):
        """记录迁移实际 SQL，确保已经规范化的数据不会被重复写入。"""
        if statement.lstrip().upper().startswith("UPDATE"):
            updates.append(statement)

    migration.upgrade()
    migration.upgrade()
    assert connection.execute(sa.select(projects.c.slideshow_config_json)).scalar_one() == current
    assert updates == []


def test_upgrade_rewrites_float_values_that_compare_equal_to_integers(migration_database):
    """JSON 数字必须真正写回整数，不能因 Python 的 5000.0 == 5000 跳过修复。"""
    migration, connection, projects, routes = migration_database
    current = default_slideshow_payload()
    current["transition"]["duration_ms"] = 400.0
    current["advance"]["delay_ms"] = 5000.0
    current["advance"]["completion_delay_ms"] = 300.0
    connection.execute(projects.insert().values(id=1, slideshow_config_json=current))
    connection.execute(routes.insert().values(id=1, route_type="page", transition_json=current["transition"], advance_json=current["advance"]))
    migration.upgrade()
    SlideshowSettings.model_validate(connection.execute(sa.select(projects.c.slideshow_config_json)).scalar_one())
    route = connection.execute(sa.select(routes)).mappings().one()
    SlideshowTransition.model_validate(route["transition_json"])
    SlideshowAdvance.model_validate(route["advance_json"])
