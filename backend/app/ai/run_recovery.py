"""文件功能：在Backend启动时收敛无法跨进程恢复的普通智能体Run。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.models.ai_agent_runtime import AiAgentRun


async def recover_interrupted_agent_runs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """终态化上个进程遗留的普通Run；暂停确认和持久化外部任务不属于本函数。"""

    recovered = 0
    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(AiAgentRun).where(AiAgentRun.status.in_(("pending", "running", "cancelling")))
                )
            ).all()
        )
        for run in runs:
            store = PlatformAgentRuntimeStore(session, user_id=run.user_id)
            if run.status == "cancelling" or run.cancel_requested_at is not None:
                await store.mark_terminal(run, status="cancelled", content="Backend重启后已完成取消。")
            else:
                await store.mark_terminal(
                    run,
                    status="failed",
                    error_code="AI_RUN_PROCESS_STOPPED",
                    error_message="Backend进程已停止，当前智能体运行无法继续执行。",
                )
            recovered += 1
    return recovered
