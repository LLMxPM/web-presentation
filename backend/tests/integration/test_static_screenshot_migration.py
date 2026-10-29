"""文件功能：验证截图选择器删列迁移保留默认任务、产物与静态去重，终止遗留动作任务。"""
import sqlite3
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _migrate(path: Path, revision: str = "head") -> None:
    """仅在当前测试临时库执行真实迁移，不读取开发数据库。"""
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path.as_posix()}", "REDIS_URL": "memory://static-migration"}
    result = subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
                            cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_drop_selector_preserves_default_jobs_and_static_dedupe(tmp_path: Path):
    """真实临时 SQLite 升级；JSON null 与 SQL NULL 都是默认静态任务，不能误取消。"""
    path = tmp_path / "static-screenshot.db"
    _migrate(path, "20261021_0100")
    with sqlite3.connect(path) as db:
        for job_id, selector, motion_hash, width, status in [
            (1, None, "", 100, "pending"),
            (2, "null", "", 200, "running"),
            (3, '{"timeline_id":"intro","at_ms":300}', "a" * 64, 100, "pending"),
            (4, '{"timeline_id":"intro","at_ms":600}', "b" * 64, 100, "succeeded"),
        ]:
            db.execute("""INSERT INTO page_screenshot_jobs
                (id, source, page_id, viewport_width, viewport_height, target_page_version_no,
                 config_hash, motion_snapshot_json, motion_snapshot_hash, status, attempt_count,
                 result_storage_key, result_sha256, created_at, updated_at)
                VALUES (?, 'test', 1, ?, 100, 1, 'static', ?, ?, ?, 0, 'preserved.png', 'sha', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (job_id, width, selector, motion_hash, status))
    _migrate(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(page_screenshot_jobs)")}
        assert not {"motion_snapshot_json", "motion_snapshot_hash", "result_applied_motion_json"} & columns
        assert {"result_storage_key", "result_sha256", "lease_expires_at", "cancel_requested_at"} <= columns
        rows = db.execute("SELECT id,status,error_code,result_storage_key FROM page_screenshot_jobs ORDER BY id").fetchall()
        assert rows == [(1, "pending", None, "preserved.png"), (2, "running", None, "preserved.png"),
                        (3, "cancelled", "SCREENSHOT_SELECTOR_REMOVED", "preserved.png"), (4, "succeeded", None, "preserved.png")]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO page_screenshot_jobs
                (source,page_id,viewport_width,viewport_height,target_page_version_no,config_hash,status,attempt_count,created_at,updated_at)
                VALUES ('test',1,100,100,1,'static','pending',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""")
