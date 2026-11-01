"""文件功能：验证截图候选编码与产物表在临时 SQLite 库上的升级、回滚及再次升级。"""

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect

from tests.fixtures.migrations import run_alembic


def test_candidate_screenshot_migration_roundtrip(tmp_path):
    """只操作测试库；回滚后历史页面仍存在，新列与表可重新创建。"""
    root = Path(__file__).resolve().parents[2]
    database = tmp_path / "validation_e2e.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}", "REDIS_URL": "memory://validation-migration"}
    for action, revision in (("upgrade", "head"), ("downgrade", "20261018_0100"), ("upgrade", "head")):
        run_alembic(root, env, revision, command=action)
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        try:
            inspector = inspect(engine)
            assert ("page_screenshot_artifacts" in inspector.get_table_names()) == (action == "upgrade")
            for table in ("ai_page_mutation_jobs", "api_mutation_jobs"):
                assert ("candidate_code" in {c["name"] for c in inspector.get_columns(table)}) == (action == "upgrade")
        finally:
            engine.dispose()
