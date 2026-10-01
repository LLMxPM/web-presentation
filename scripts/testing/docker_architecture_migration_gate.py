"""文件功能：在真实 Alembic 首个新增列 DDL 完成后挂起，用于迁移容器 SIGKILL 故障注入。"""

import os
import time
from pathlib import Path

from alembic.config import CommandLine
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "after_cursor_execute")
def stop_after_ddl(_connection, _cursor, statement, _parameters, _context, _executemany) -> None:
    """只延迟真实 DDL 后的执行，不改 SQL/schema/revision；marker 仅保存在演练数据卷。"""
    if "ALTER TABLE ai_agent_runs ADD COLUMN process_owner" in statement:
        marker = Path("/app/backend/data/m05-migration-gate")
        marker.write_text("actual-ddl-executed", encoding="utf-8")
        while marker.exists():
            time.sleep(0.1)


if __name__ == "__main__":
    if os.environ.get("DATABASE_URL") != "sqlite+aiosqlite:////app/backend/data/m05.db":
        raise ValueError("迁移故障注入只允许演练 m05.db")
    CommandLine().main(["upgrade", "head"])
