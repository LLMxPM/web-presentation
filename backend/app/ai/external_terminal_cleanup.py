"""文件功能：以集合式数据库操作收敛终态Run遗留的外部任务状态。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun, AiAgentToolCall
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask

_RUN_TERMINAL = frozenset({"completed", "cancelled", "failed"})
_TASK_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


@dataclass(frozen=True)
class TerminalRunCleanupResult:
    """记录本轮各类集合式清理实际影响的行数。"""

    tasks: int
    batches: int
    requirements: int
    tool_calls: int


async def cleanup_terminal_run_external_state(
    session: AsyncSession,
    *,
    now: datetime,
) -> TerminalRunCleanupResult:
    """清理终态Run的可执行外部状态，同时保留仍持有有效租约的续跑Batch。"""

    eligible_run_ids = select(AiAgentRun.run_id).where(
        AiAgentRun.status.in_(_RUN_TERMINAL),
        ~exists().where(
            AiAgentExternalBatch.run_id == AiAgentRun.run_id,
            AiAgentExternalBatch.status == "resuming",
            AiAgentExternalBatch.lease_expires_at.is_not(None),
            AiAgentExternalBatch.lease_expires_at > now,
        ),
    )

    task_result = await session.execute(
        update(AiAgentExternalTask)
        .where(
            AiAgentExternalTask.run_id.in_(eligible_run_ids),
            AiAgentExternalTask.status.not_in(_TASK_TERMINAL),
            or_(
                AiAgentExternalTask.cancel_requested_at.is_(None),
                AiAgentExternalTask.status == "pending",
            ),
        )
        .values(
            cancel_requested_at=func.coalesce(AiAgentExternalTask.cancel_requested_at, now),
            status=case(
                (AiAgentExternalTask.status == "pending", "cancelled"),
                else_=AiAgentExternalTask.status,
            ),
            finished_at=case(
                (AiAgentExternalTask.status == "pending", now),
                else_=AiAgentExternalTask.finished_at,
            ),
        )
        .execution_options(synchronize_session=False)
    )
    batch_result = await session.execute(
        update(AiAgentExternalBatch)
        .where(
            AiAgentExternalBatch.run_id.in_(eligible_run_ids),
            AiAgentExternalBatch.status.in_(("collecting", "waiting_tasks", "ready")),
        )
        .values(status="cancelled", finished_at=now)
        .execution_options(synchronize_session=False)
    )
    requirement_result = await session.execute(
        update(AiAgentRequirement)
        .where(
            AiAgentRequirement.run_id.in_(eligible_run_ids),
            AiAgentRequirement.status.in_(("pending", "resolving")),
        )
        .values(status="cancelled", resolved_at=now)
        .execution_options(synchronize_session=False)
    )
    tool_call_result = await session.execute(
        update(AiAgentToolCall)
        .where(
            AiAgentToolCall.run_id.in_(eligible_run_ids),
            AiAgentToolCall.status.in_(("running", "waiting_external")),
        )
        .values(status="cancelled", message="父级运行已终态。")
        .execution_options(synchronize_session=False)
    )
    return TerminalRunCleanupResult(
        tasks=int(task_result.rowcount or 0),
        batches=int(batch_result.rowcount or 0),
        requirements=int(requirement_result.rowcount or 0),
        tool_calls=int(tool_call_result.rowcount or 0),
    )
