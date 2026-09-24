"""文件功能：提供跨数据库兼容的运行事件游标原子分配能力。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.run_write_fence import AgentRunWriteFence, AgentRunWriteFenceLost
from app.models.ai_agent_runtime import AiAgentRun


async def allocate_run_event_index(
    session: AsyncSession,
    *,
    run_id: str,
    updated_at: datetime,
    require_active: bool = False,
    write_fence: AgentRunWriteFence | None = None,
) -> int:
    """原子递增指定 run 的事件游标；可把后台续跑租约围栏并入同一条写入。"""

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
    if write_fence is not None:
        statement = statement.where(write_fence.condition(updated_at))
    result = await session.execute(statement)
    event_index = result.scalar_one_or_none()
    if event_index is None:
        if write_fence is not None and not await write_fence.is_owned(session, now=updated_at):
            raise AgentRunWriteFenceLost("后台 AI 页面变更续跑租约已失效。")
        status = await session.scalar(select(AiAgentRun.status).where(AiAgentRun.run_id == run_id))
        if status is None:
            raise ValueError("AI_RUN_NOT_FOUND")
        raise ValueError("AI_RUN_TERMINAL")
    return int(event_index)
