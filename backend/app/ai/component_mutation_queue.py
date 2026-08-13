"""文件功能：认领并执行组件外部任务，维护通用Task租约、取消与终态。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.component_mutation_executor import AiComponentMutationExecutor
from app.ai.platform_tools import is_recoverable_tool_error_result
from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask, AiComponentMutationTask
from app.services.durable_job_lease_service import (
    claim_pending_jobs,
    renew_running_job_lease,
    transition_owned_running_job,
)

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3


async def run_ai_component_mutation_queue_loop(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """启动组件外部任务Worker。"""

    settings = get_settings()
    concurrency = max(1, int(getattr(settings, "ai_page_mutation_concurrency", 1)))
    workers = [
        asyncio.create_task(
            _run_worker(session_factory, worker_id=f"ai-component-{uuid4().hex[:12]}"),
            name=f"ai-component-mutation-worker-{index + 1}",
        )
        for index in range(concurrency)
    ]
    try:
        await asyncio.gather(*workers)
    finally:
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker


async def recover_interrupted_component_mutation_tasks(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """启动时恢复租约过期的组件任务。"""

    now = utc_now()
    recovered = 0
    async with session_factory() as session:
        tasks = list(
            (
                await session.scalars(
                    select(AiAgentExternalTask).where(
                        AiAgentExternalTask.kind == "component_mutation",
                        AiAgentExternalTask.status == "running",
                        (AiAgentExternalTask.lease_expires_at.is_(None))
                        | (AiAgentExternalTask.lease_expires_at <= now),
                    )
                )
            ).all()
        )
        for task in tasks:
            if task.cancel_requested_at is not None:
                task.status = "cancelled"
                task.finished_at = now
            elif task.attempt_count < _MAX_ATTEMPTS:
                task.status = "pending"
                task.started_at = None
            else:
                task.status = "failed"
                task.error_code = "AI_COMPONENT_MUTATION_INTERRUPTED"
                task.error_message = "组件任务执行中断且已达到最大重试次数。"
                task.finished_at = now
            task.worker_id = None
            task.lease_expires_at = None
            task.heartbeat_at = None
            recovered += 1
        await session.commit()
    return recovered


async def _run_worker(session_factory: async_sessionmaker[AsyncSession], *, worker_id: str) -> None:
    """循环认领已封口且父Run仍在等待的组件Task。"""

    settings = get_settings()
    poll_interval = max(0.05, float(settings.ai_page_mutation_poll_interval_seconds))
    lease_seconds = max(int(settings.durable_job_lease_seconds), int(settings.durable_job_heartbeat_seconds) * 3)
    while True:
        try:
            async with session_factory() as session:
                candidate = (
                    select(AiAgentExternalTask.id)
                    .join(AiAgentExternalBatch, AiAgentExternalBatch.batch_id == AiAgentExternalTask.batch_id)
                    .join(AiAgentRun, AiAgentRun.run_id == AiAgentExternalTask.run_id)
                    .where(
                        AiAgentExternalTask.kind == "component_mutation",
                        AiAgentExternalTask.status == "pending",
                        AiAgentExternalTask.cancel_requested_at.is_(None),
                        AiAgentExternalBatch.status == "waiting_tasks",
                        AiAgentRun.status == "waiting_external",
                        AiAgentRun.cancel_requested_at.is_(None),
                    )
                    .order_by(AiAgentExternalTask.created_at.asc(), AiAgentExternalTask.id.asc())
                )
                claimed = await claim_pending_jobs(
                    session,
                    AiAgentExternalTask,
                    worker_id=worker_id,
                    limit=1,
                    lease_seconds=lease_seconds,
                    candidate_query=candidate,
                )
            if not claimed:
                await asyncio.sleep(poll_interval)
                continue
            await _execute_claimed(session_factory, task_row_id=claimed[0], worker_id=worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("组件外部任务Worker异常。", extra={"event": "ai.component.worker.failed"})
            await asyncio.sleep(poll_interval)


async def _execute_claimed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    task_row_id: int,
    worker_id: str,
) -> None:
    """执行单个组件Task，并以Task租约作为最终业务写入围栏。"""

    heartbeat = asyncio.create_task(
        _heartbeat(session_factory, task_row_id=task_row_id, worker_id=worker_id),
        name=f"ai-component-heartbeat-{task_row_id}",
    )
    try:
        async with session_factory() as session:
            task = await session.get(AiAgentExternalTask, task_row_id)
            if task is None or task.status != "running" or task.worker_id != worker_id:
                return
            run = await session.get(AiAgentRun, task.run_id)
            detail = await session.get(AiComponentMutationTask, task.task_id)
            if run is None or detail is None:
                await _fail_task(session, task=task, worker_id=worker_id, code="AI_COMPONENT_TASK_INVALID", message="组件任务关联数据不存在。")
                return
            if run.cancel_requested_at is not None or run.status != "waiting_external" or task.cancel_requested_at is not None:
                await _cancel_task(session, task=task, worker_id=worker_id)
                return
            result = await AiComponentMutationExecutor(session).execute(detail, operator_id=run.user_id)
            # Runtime检查后、业务提交前再次核对Run取消与Task租约，防止迟到写入。
            await session.refresh(task)
            await session.refresh(run)
            if run.cancel_requested_at is not None or task.cancel_requested_at is not None:
                await session.rollback()
                async with session_factory() as cancel_session:
                    current = await cancel_session.get(AiAgentExternalTask, task_row_id)
                    if current is not None:
                        await _cancel_task(cancel_session, task=current, worker_id=worker_id)
                return
            transitioned = await transition_owned_running_job(
                session,
                AiAgentExternalTask,
                job_id=task_row_id,
                worker_id=worker_id,
                require_not_cancelled=True,
                require_active_lease=True,
                values={
                    "status": "succeeded",
                    "result_json": result,
                    "result_summary_json": {
                        "kind": "component_mutation",
                        "success": bool(result.get("success")),
                        "recoverable_error": is_recoverable_tool_error_result(result),
                        "component_id": result.get("component_id"),
                    },
                    "progress_at": utc_now(),
                    "finished_at": utc_now(),
                    "worker_id": None,
                    "lease_expires_at": None,
                    "heartbeat_at": None,
                },
                commit=False,
            )
            if not transitioned:
                await session.rollback()
                return
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.exception("组件外部任务执行失败。", extra={"task_id": task_row_id})
        async with session_factory() as session:
            task = await session.get(AiAgentExternalTask, task_row_id)
            if task is not None:
                await _fail_task(
                    session,
                    task=task,
                    worker_id=worker_id,
                    code="AI_COMPONENT_MUTATION_FAILED",
                    message=str(exc)[:2000],
                )
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _heartbeat(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    task_row_id: int,
    worker_id: str,
) -> None:
    """周期续租组件Task；丢失租约时自然停止。"""

    settings = get_settings()
    interval = max(1, int(settings.durable_job_heartbeat_seconds))
    lease_seconds = max(int(settings.durable_job_lease_seconds), interval * 3)
    while True:
        await asyncio.sleep(interval)
        async with session_factory() as session:
            if not await renew_running_job_lease(
                session,
                AiAgentExternalTask,
                job_id=task_row_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            ):
                return


async def _fail_task(
    session: AsyncSession,
    *,
    task: AiAgentExternalTask,
    worker_id: str,
    code: str,
    message: str,
) -> None:
    """由租约持有者把组件Task收敛为失败。"""

    await transition_owned_running_job(
        session,
        AiAgentExternalTask,
        job_id=task.id,
        worker_id=worker_id,
        values={
            "status": "failed",
            "error_code": code,
            "error_message": message,
            "finished_at": utc_now(),
            "worker_id": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
        },
    )


async def _cancel_task(session: AsyncSession, *, task: AiAgentExternalTask, worker_id: str) -> None:
    """由当前Worker确认取消并撤销组件写入权。"""

    await transition_owned_running_job(
        session,
        AiAgentExternalTask,
        job_id=task.id,
        worker_id=worker_id,
        values={
            "status": "cancelled",
            "finished_at": utc_now(),
            "worker_id": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
        },
    )
