"""文件功能：真实子进程在迁移 DDL 后突然退出，验证 SQLite schema 与 Alembic revision 原子回滚。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(("revision", "ddl", "column_present"), [
    ("20260926_0100", "ALTER TABLE ai_agent_runs ADD COLUMN process_owner", False),
    ("20260929_0100", "ALTER TABLE ai_page_mutation_batches DROP COLUMN lease_generation", True),
])
def test_sqlite_migration_abrupt_exit_rolls_back_ddl_and_revision(tmp_path: Path, revision: str, ddl: str, column_present: bool) -> None:
    """不是异常回滚模拟：DDL 已真实执行后 os._exit，旧列/revision/历史行必须共同保留且可重试。"""
    backend = Path(__file__).resolve().parents[2]
    database = tmp_path / "interrupted.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}", "REDIS_URL": "memory://migration-interrupt"}
    command = [sys.executable, "-m", "alembic", "upgrade"]
    baseline = subprocess.run([*command, revision], cwd=backend, env=env, capture_output=True, text=True, check=False)
    assert baseline.returncode == 0, baseline.stderr
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE interruption_sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO interruption_sentinel VALUES ('preserved')")
    code = f"""import os
from sqlalchemy import event
from sqlalchemy.engine import Engine
from alembic.config import CommandLine
@event.listens_for(Engine, 'after_cursor_execute')
def interrupt(connection,cursor,statement,parameters,context,executemany):
 if {ddl!r} in statement:
  os._exit(91)
CommandLine().main(['upgrade','head'])
"""
    fault = subprocess.run([sys.executable, "-c", code], cwd=backend, env=env, capture_output=True, text=True, check=False)
    assert fault.returncode == 91, fault.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == revision
        table, column = ("ai_agent_runs", "process_owner") if not column_present else ("ai_page_mutation_batches", "lease_generation")
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        assert (column in columns) == column_present
        assert connection.execute("SELECT value FROM interruption_sentinel").fetchall() == [("preserved",)]
    retry = subprocess.run([*command, "head"], cwd=backend, env=env, capture_output=True, text=True, check=False)
    assert retry.returncode == 0, retry.stderr
