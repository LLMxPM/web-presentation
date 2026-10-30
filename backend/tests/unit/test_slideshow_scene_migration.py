"""文件功能：在 SQLite 实际执行与 PostgreSQL 离线 DDL 验证 schema 4 默认升级，不运行开发数据库迁移。"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration():
    """独立加载当前迁移，不修改包路径或运行整个应用。"""
    path = Path(__file__).resolve().parents[2] / "migrations/versions/20261030_0100_scene_slideshow_default.py"
    spec = importlib.util.spec_from_file_location("scene_slideshow_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sqlite_default_upgrade_keeps_existing_configuration() -> None:
    """升级只改变默认，旧行不被静默映射；新建行使用当前默认，降级仅恢复默认结构。"""
    migration = _migration()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE projects (id INTEGER PRIMARY KEY, slideshow_config_json JSON NOT NULL DEFAULT '{}')"))
        connection.execute(sa.text("INSERT INTO projects (id, slideshow_config_json) VALUES (1, :value)"), {"value": json.dumps({"old": True})})
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(sa.text("INSERT INTO projects (id) VALUES (2)"))
        rows = connection.execute(sa.text("SELECT id, slideshow_config_json FROM projects ORDER BY id")).all()
        assert json.loads(rows[0][1]) == {"old": True}
        assert json.loads(rows[1][1]) == migration._V4
        migration.downgrade()
        connection.execute(sa.text("INSERT INTO projects (id) VALUES (3)"))
        assert json.loads(connection.execute(sa.text("SELECT slideshow_config_json FROM projects WHERE id=3")).scalar_one()) == migration._V3
    engine.dispose()


def test_postgresql_default_ddl_has_no_json_bind_parameter_substitution() -> None:
    """离线编译同一迁移，保证 JSON 冒号不被当成绑定变量；不宣称真实 PG 升级通过。"""
    migration = _migration()
    buffer = io.StringIO()
    migration.op = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer}))
    migration.upgrade()
    sql = buffer.getvalue()
    assert "ALTER TABLE projects ALTER COLUMN slideshow_config_json SET DEFAULT" in sql
    assert '"completion_delay_ms":300' in sql
    assert "auto_start" not in sql
