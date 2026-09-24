"""文件功能：以集合式数据库操作收敛终态Run遗留的外部任务状态。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, case, exists, func, or_, select, update
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

    async def cancel_when_present(
        model: type[Any],
        probe_column: Any,
        conditions: Sequence[ColumnElement[bool]],
        values: dict[str, Any],
    ) -> int:
        """命中集非空才发 UPDATE；探测与更新共用同一组条件，杜绝谓词漂移。

        空闲免写避免 2Hz 无条件写 DML（对齐 durable_job 空闲免写模式）。
        probe_column 只取主键，不把 result_json/input_payload_json 等大列读进内存。
        """

        hit = await session.scalar(select(probe_column).where(*conditions).limit(1))
        if hit is None:
            return 0
        result = await session.execute(
            update(model).where(*conditions).values(**values).execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

    tasks = await cancel_when_present(
        AiAgentExternalTask,
        AiAgentExternalTask.task_id,
        [
            AiAgentExternalTask.run_id.in_(eligible_run_ids),
            AiAgentExternalTask.status.not_in(_TASK_TERMINAL),
            or_(
                AiAgentExternalTask.cancel_requested_at.is_(None),
                AiAgentExternalTask.status == "pending",
            ),
        ],
        {
            "cancel_requested_at": func.coalesce(AiAgentExternalTask.cancel_requested_at, now),
            "status": case(
                (AiAgentExternalTask.status == "pending", "cancelled"),
                else_=AiAgentExternalTask.status,
            ),
            "finished_at": case(
                (AiAgentExternalTask.status == "pending", now),
                else_=AiAgentExternalTask.finished_at,
            ),
        },
    )
    batches = await cancel_when_present(
        AiAgentExternalBatch,
        AiAgentExternalBatch.batch_id,
        [
            AiAgentExternalBatch.run_id.in_(eligible_run_ids),
            AiAgentExternalBatch.status.in_(("collecting", "waiting_tasks", "ready")),
        ],
        {"status": "cancelled", "finished_at": now},
    )
    requirements = await cancel_when_present(
        AiAgentRequirement,
        AiAgentRequirement.id,
        [
            AiAgentRequirement.run_id.in_(eligible_run_ids),
            AiAgentRequirement.status.in_(("pending", "resolving")),
        ],
        {"status": "cancelled", "resolved_at": now},
    )
    tool_calls = await cancel_when_present(
        AiAgentToolCall,
        AiAgentToolCall.id,
        [
            AiAgentToolCall.run_id.in_(eligible_run_ids),
            AiAgentToolCall.status.in_(("running", "waiting_external")),
        ],
        {"status": "cancelled", "message": "父级运行已终态。"},
    )
    return TerminalRunCleanupResult(
        tasks=tasks,
        batches=batches,
        requirements=requirements,
        tool_calls=tool_calls,
    )
