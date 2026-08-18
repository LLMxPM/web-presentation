"""文件功能：提供统一外部 Batch/Task 的入队、封口、状态镜像与结果消费服务。"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.task_states import EXTERNAL_TASK_TRANSITIONS, ensure_state_transition
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun, AiAgentToolCall
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask


def stable_external_identifier(prefix: str, *parts: str) -> str:
    """按业务身份生成稳定ID，确保工具重试不会重复创建任务。"""

    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"ai-external-{prefix}-{digest}"


async def enqueue_external_task(
    session: AsyncSession,
    *,
    run: AiAgentRun,
    kind: str,
    tool_call_id: str,
    deferred_tool_call_id: str,
) -> AiAgentExternalTask:
    """创建或复用当前执行阶段的统一外部任务，并归入唯一 collecting Batch。"""

    existing = await session.scalar(
        select(AiAgentExternalTask).where(
            AiAgentExternalTask.run_id == run.run_id,
            AiAgentExternalTask.tool_call_id == tool_call_id,
        )
    )
    if existing is not None:
        return existing
    batch = await session.scalar(
        select(AiAgentExternalBatch)
        .where(
            AiAgentExternalBatch.run_id == run.run_id,
            AiAgentExternalBatch.status == "collecting",
        )
        .order_by(AiAgentExternalBatch.sequence_no.desc())
        .limit(1)
    )
    if batch is None:
        sequence_no = int(
            await session.scalar(
                select(func.max(AiAgentExternalBatch.sequence_no)).where(AiAgentExternalBatch.run_id == run.run_id)
            )
            or 0
        ) + 1
        batch = AiAgentExternalBatch(
            batch_id=stable_external_identifier("batch", run.run_id, str(sequence_no)),
            run_id=run.run_id,
            session_id=run.session_id,
            sequence_no=sequence_no,
            status="collecting",
        )
        session.add(batch)
        await session.flush([batch])
    task = AiAgentExternalTask(
        task_id=stable_external_identifier("task", run.run_id, tool_call_id),
        batch_id=batch.batch_id,
        run_id=run.run_id,
        session_id=run.session_id,
        kind=kind,
        tool_call_id=tool_call_id,
        deferred_tool_call_id=deferred_tool_call_id,
        status="pending",
        progress_at=utc_now(),
    )
    session.add(task)
    await session.flush([task])
    return task


async def seal_external_batch_for_requirement(
    session: AsyncSession,
    *,
    run: AiAgentRun,
    requirement: AiAgentRequirement,
) -> AiAgentExternalBatch:
    """把 Deferred Requirement 与 collecting Batch 原子绑定，并更新工具等待态。"""

    batch = await session.scalar(
        select(AiAgentExternalBatch)
        .where(
            AiAgentExternalBatch.run_id == run.run_id,
            AiAgentExternalBatch.status == "collecting",
        )
        .order_by(AiAgentExternalBatch.sequence_no.desc())
        .limit(1)
    )
    if batch is None:
        raise AppException(
            status_code=409,
            code="AI_EXTERNAL_BATCH_MISSING",
            detail="外部任务缺少正在收集的批次。",
        )
    task_count = int(
        await session.scalar(select(func.count(AiAgentExternalTask.id)).where(AiAgentExternalTask.batch_id == batch.batch_id))
        or 0
    )
    if task_count == 0:
        raise AppException(status_code=409, code="AI_EXTERNAL_BATCH_EMPTY", detail="外部任务批次没有任务。")
    batch.requirement_id = requirement.requirement_id
    batch.status = "waiting_tasks"
    batch.updated_at = utc_now()
    tool_ids = list(
        (await session.scalars(select(AiAgentExternalTask.tool_call_id).where(AiAgentExternalTask.batch_id == batch.batch_id))).all()
    )
    tool_calls = list(
        (
            await session.scalars(
                select(AiAgentToolCall).where(
                    AiAgentToolCall.run_id == run.run_id,
                    AiAgentToolCall.tool_call_id.in_(tool_ids),
                    AiAgentToolCall.status == "running",
                )
            )
        ).all()
    )
    for tool_call in tool_calls:
        tool_call.status = "waiting_external"
    return batch


async def transition_external_task(
    session: AsyncSession,
    task: AiAgentExternalTask,
    *,
    status: str,
    result: Any | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """按统一状态机迁移Task，并同步租约和终态时间字段。"""

    ensure_state_transition(
        current=task.status,
        target=status,
        transitions=EXTERNAL_TASK_TRANSITIONS,
        entity="external_task",
    )
    now = utc_now()
    task.status = status
    task.progress_at = now
    task.result_json = result if result is not None else task.result_json
    task.error_code = error_code
    task.error_message = error_message
    if status in {"succeeded", "failed", "cancelled"}:
        task.finished_at = now
        task.worker_id = None
        task.lease_expires_at = None
        task.heartbeat_at = None


async def consume_external_batch_results(
    session: AsyncSession,
    *,
    batch: AiAgentExternalBatch,
) -> None:
    """回灌成功后清理完整结果，只保留小型摘要和消费时间。"""

    now = utc_now()
    tasks = list((await session.scalars(select(AiAgentExternalTask).where(AiAgentExternalTask.batch_id == batch.batch_id))).all())
    for task in tasks:
        value = task.result_json
        summary: dict[str, Any] = {"kind": task.kind, "status": task.status}
        if isinstance(value, dict):
            for key in ("page_id", "component_id", "job_id", "status", "success", "applied"):
                if key in value:
                    summary[key] = value[key]
        task.result_summary_json = summary
        task.result_json = None
        task.result_consumed_at = now
    batch.status = "completed"
    batch.finished_at = now
    batch.worker_id = None
    batch.lease_expires_at = None
    batch.heartbeat_at = None


def external_lease_duration(*, lease_seconds: int, heartbeat_seconds: int) -> timedelta:
    """规范统一租约时长，并保证至少覆盖三个心跳周期。"""

    return timedelta(seconds=max(int(lease_seconds), int(heartbeat_seconds) * 3, 1))
