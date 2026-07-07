"""文件功能：验证 Alembic 完整迁移可在 SQLite 轻量部署数据库上执行。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_alembic_head_should_migrate_sqlite_database(tmp_path: Path) -> None:
    """SQLite 模式应能从空库迁移到当前 head，保障轻量部署首次启动可用。"""

    backend_root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "web_presentation.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    env["REDIS_URL"] = "memory://sqlite-migration-test"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=backend_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert database_path.exists()
