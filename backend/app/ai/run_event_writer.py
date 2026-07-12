"""文件功能：提供跨数据库兼容的运行事件游标原子分配与 SQLite 写冲突识别能力。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_agent_runtime import AiAgentRun

SQLITE_BUSY_ERROR_CODE = 5
SQLITE_LOCKED_ERROR_CODE = 6
SQLITE_LOCK_MESSAGES = ("database is locked", "database table is locked")


async def allocate_run_event_index(
    session: AsyncSession,
    *,
    run_id: str,
    updated_at: datetime,
    require_active: bool = False,
) -> int:
    """原子递增指定 run 的事件游标；成员事件可同时约束父 run 尚未终止。"""

    statement = (
        update(AiAgentRun)
        .where(AiAgentRun.run_id == run_id)
        .values(
            event_index=AiAgentRun.event_index + 1,
            updated_at=updated_at,
        )
        .returning(AiAgentRun.event_index)
        .execution_options(synchronize_session=False)
    )
    if require_active:
        statement = statement.where(AiAgentRun.status.not_in({"completed", "cancelled", "failed"}))
    result = await session.execute(statement)
    event_index = result.scalar_one_or_none()
    if event_index is None:
        status = await session.scalar(select(AiAgentRun.status).where(AiAgentRun.run_id == run_id))
        if status is None:
            raise ValueError("AI_RUN_NOT_FOUND")
        raise ValueError("AI_RUN_TERMINAL")
    return int(event_index)


def is_sqlite_lock_error(session: AsyncSession, exc: OperationalError) -> bool:
    """判断异常是否来自当前 SQLite 会话的 BUSY/LOCKED 写冲突。"""

    if session.get_bind().dialect.name != "sqlite":
        return False
    original_error = exc.orig
    sqlite_error_code = getattr(original_error, "sqlite_errorcode", None)
    if isinstance(sqlite_error_code, int) and sqlite_error_code & 0xFF in {
        SQLITE_BUSY_ERROR_CODE,
        SQLITE_LOCKED_ERROR_CODE,
    }:
        return True
    message = str(original_error).lower()
    return any(fragment in message for fragment in SQLITE_LOCK_MESSAGES)
