"""文件功能：运行 AI 页面变更持久化队列、租约心跳与取消协调。

模型续跑统一由 external coordinator 认领 AiAgentExternalBatch 完成；
本模块只负责 AiPageMutationJob 领域执行，并把终态写穿到 AiAgentExternalTask。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime
from time import monotonic
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.external_task_control import sync_external_task_from_domain_job
from app.ai.page_mutation_executor import AiPageMutationExecutor
from app.ai.page_mutation_wakeup import page_mutation_job_wakeup
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_page_mutation import AiPageMutationBatch, AiPageMutationJob
from app.schemas.agent import AgentRunEvent
from app.services.durable_job_lease_service import (
    claim_pending_jobs,
    recover_expired_running_jobs,
    renew_running_job_lease,
    transition_owned_running_job,
)

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_ACTIVE_JOB_STATUSES = ("pending", "running")
_FATAL_PERMISSION_ERROR_PREFIX = "AUTH_PERMISSION_DENIED"
_RETRYABLE_RUNTIME_QUEUE_ERROR_CODES = {"RUNTIME_VITE_QUEUE_FULL", "RUNTIME_VITE_QUEUE_TIMEOUT"}


async def run_ai_page_mutation_queue_loop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """启动配置数量的页面变更领域 Worker。"""

    settings = get_settings()
    concurrency = max(1, int(getattr(settings, "ai_page_mutation_concurrency", 1)))
    workers = [
        asyncio.create_task(
            _run_job_worker(session_factory, worker_id=f"ai-page-job-{uuid4().hex[:12]}"),
            name=f"ai-page-mutation-worker-{index + 1}",
        )
        for index in range(concurrency)
    ]
    try:
        await asyncio.gather(*workers)
    finally:
        for task in workers:
            task.cancel()
        for task in workers:
            with suppress(asyncio.CancelledError):
                await task


async def recover_interrupted_ai_page_mutation_jobs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """恢复过期领域 Job，并收敛历史遗留的页面 Batch 续跑残留。"""

    async with session_factory() as session:
        summary = await recover_expired_running_jobs(
            session,
            AiPageMutationJob,
            max_attempts=_MAX_ATTEMPTS,
            interrupted_error_code="AI_PAGE_MUTATION_INTERRUPTED",
            interrupted_error_message="页面变更任务执行中断且已达到最大重试次数。",
        )
    recovered_batches = await _finalize_legacy_resuming_batches(session_factory)
    total = summary.total_count + recovered_batches
    if total:
        logger.warning(
            "恢复了中断的 AI 页面变更任务。",
            extra={"event": "ai.page_mutation.recovered", "count": total},
        )
    return total


async def _finalize_legacy_resuming_batches(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """把迁移前留下的页面 Batch resuming 记录收敛为 completed。

    模型续跑已统一到 AiAgentExternalBatch；这里只清理旧状态机残留，
    不再改写 Run 或 Requirement，避免与 external coordinator 双轨恢复。
    """

    now = utc_now()
    async with session_factory() as session:
        result = await session.execute(
            update(AiPageMutationBatch)
            .where(AiPageMutationBatch.status == "resuming")
            .values(
                status="completed",
                finished_at=now,
                worker_id=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0):
            await session.commit()
            return int(result.rowcount or 0)
        await session.commit()
    return 0


async def _run_job_worker(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    worker_id: str,
) -> None:
    """持续认领单个页面变更任务，并确保同一 Worker 内串行执行。"""

    settings = get_settings()
    poll_interval = max(0.05, float(getattr(settings, "ai_page_mutation_poll_interval_seconds", 0.5)))
    lease_seconds = max(1, int(getattr(settings, "durable_job_lease_seconds", 300)))
    executor = AiPageMutationExecutor(session_factory)
    idle_reconcile_counter = 0
    while True:
        try:
            observed_generation = page_mutation_job_wakeup.generation
            async with session_factory() as session:
                candidate_query = (
                    select(AiPageMutationJob.id)
                    .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationJob.run_id)
                    .where(
                        AiPageMutationJob.status == "pending",
                        AiPageMutationJob.cancel_requested_at.is_(None),
                        AiAgentRun.status == "waiting_external",
                        AiAgentRun.cancel_requested_at.is_(None),
                    )
                    .order_by(AiPageMutationJob.created_at.asc(), AiPageMutationJob.id.asc())
                )
                claimed = await claim_pending_jobs(
                    session,
                    AiPageMutationJob,
                    worker_id=worker_id,
                    limit=1,
                    lease_seconds=lease_seconds,
                    candidate_query=candidate_query,
                )
            if not claimed:
                idle_reconcile_counter += 1
                if idle_reconcile_counter >= 4:
                    idle_reconcile_counter = 0
                    await _reconcile_cancelled_and_orphaned_jobs(session_factory)
                await page_mutation_job_wakeup.wait(observed_generation, poll_interval)
                continue
            idle_reconcile_counter = 0
            await _execute_claimed_job(
                session_factory,
                executor=executor,
                database_id=claimed[0],
                worker_id=worker_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("AI 页面变更 Worker 循环异常。", extra={"event": "ai.page_mutation.worker.failed"})
            await asyncio.sleep(poll_interval)


async def _execute_claimed_job(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    executor: AiPageMutationExecutor,
    database_id: int,
    worker_id: str,
) -> None:
    """在租约心跳保护下执行任务，并按错误类型决定回灌、重试或失败。"""

    lease_lost = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_job_lease(
            session_factory,
            database_id=database_id,
            worker_id=worker_id,
            lease_lost=lease_lost,
        ),
        name=f"ai-page-mutation-heartbeat-{database_id}",
    )
    execution_started_at = monotonic()

    async def progress(phase: str) -> None:
        """只在阶段变化时追加进度事件，避免心跳写放大 AI 事件表。"""

        await _append_progress_event(
            session_factory,
            database_id=database_id,
            worker_id=worker_id,
            phase=phase,
        )

    try:
        await executor.execute(
            database_id=database_id,
            worker_id=worker_id,
            progress=progress,
            lease_lost=lease_lost,
        )
        # 代码校验或浏览器任务结束时，取消请求可能刚好落在 Executor 的
        # “无需写页面”分支之后。此处由仍持有 Job 的 Worker 收敛取消终态，
        # 避免把已停止的执行留到租约过期后才恢复。
        await _transition_cancel_requested_job_if_owned(
            session_factory,
            database_id=database_id,
            worker_id=worker_id,
        )
    except AppException as exc:
        if exc.code == "AI_RUN_CANCELLED":
            await _transition_job_cancelled(session_factory, database_id=database_id, worker_id=worker_id)
        elif exc.code == "AI_PAGE_MUTATION_LEASE_LOST":
            logger.info("AI 页面变更任务已失去租约，旧 Worker 放弃结果。", extra={"job_id": database_id})
        elif _is_permission_denied_error(exc):
            await _transition_job_failed(
                session_factory,
                database_id=database_id,
                worker_id=worker_id,
                code=_fatal_permission_error_code(exc.code),
                message=exc.detail,
            )
        elif _is_retryable_infrastructure_error(exc):
            await _retry_or_fail_job(
                session_factory,
                database_id=database_id,
                worker_id=worker_id,
                code=exc.code,
                message=exc.detail,
            )
        elif exc.status_code < 500:
            await executor.complete_business_error(
                database_id=database_id,
                worker_id=worker_id,
                error=exc,
            )
        else:
            await _retry_or_fail_job(
                session_factory,
                database_id=database_id,
                worker_id=worker_id,
                code=exc.code,
                message=exc.detail,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "AI 页面变更任务执行失败。",
            extra={"event": "ai.page_mutation.failed", "job_id": database_id},
        )
        await _retry_or_fail_job(
            session_factory,
            database_id=database_id,
            worker_id=worker_id,
            code="AI_PAGE_MUTATION_EXECUTION_FAILED",
            message=str(exc)[:2000] or "页面变更任务执行失败。",
        )
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat
        await _sync_external_after_execution(session_factory, database_id=database_id)
        logger.info(
            "AI 页面变更任务本次执行结束。",
            extra={
                "event": "ai.page_mutation.job.execution_finished",
                "job_id": database_id,
                "worker_id": worker_id,
                "duration_ms": round((monotonic() - execution_started_at) * 1000, 2),
            },
        )


async def _sync_external_after_execution(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
) -> None:
    """把领域 Job 最新状态写穿到统一 ExternalTask，缩短续跑就绪窗口。"""

    try:
        async with session_factory() as session:
            job = await session.get(AiPageMutationJob, database_id)
            if job is None:
                return
            synced = await sync_external_task_from_domain_job(session, job=job)
            if synced:
                await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning(
            "页面变更终态写穿统一外部任务失败，交由协调器对账。",
            exc_info=True,
            extra={"event": "ai.page_mutation.external_sync_failed", "job_id": database_id},
        )


async def _append_progress_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
    phase: str,
) -> None:
    """追加低频工具阶段事件，事件写入失败不影响页面任务本身。"""

    try:
        async with session_factory() as session:
            job = await session.scalar(
                select(AiPageMutationJob).where(
                    AiPageMutationJob.id == database_id,
                    AiPageMutationJob.status == "running",
                    AiPageMutationJob.worker_id == worker_id,
                    AiPageMutationJob.lease_expires_at.is_not(None),
                    AiPageMutationJob.lease_expires_at > utc_now(),
                )
            )
            if job is None:
                return
            run = await session.get(AiAgentRun, job.run_id)
            if run is None:
                return
            await PlatformAgentRuntimeStore(session, user_id=run.user_id).append_event(
                run,
                AgentRunEvent(
                    event="tool.progress",
                    run_id=run.run_id,
                    session_id=run.session_id,
                    data={
                        "tool_call_id": job.tool_call_id,
                        "tool_name": _display_tool_name(job.operation),
                        "job_id": job.job_id,
                        "phase": phase,
                    },
                ),
            )
    except Exception:  # noqa: BLE001
        logger.warning("写入 AI 页面变更进度事件失败。", exc_info=True, extra={"job_id": database_id, "phase": phase})


async def _heartbeat_job_lease(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
    lease_lost: asyncio.Event,
) -> None:
    """在独立短会话中续租 Job；续租失败时阻止旧 Worker 提交迟到结果。"""

    settings = get_settings()
    heartbeat_seconds = max(1, int(getattr(settings, "durable_job_heartbeat_seconds", 30)))
    lease_seconds = max(heartbeat_seconds + 1, int(getattr(settings, "durable_job_lease_seconds", 300)))
    while True:
        try:
            await asyncio.sleep(heartbeat_seconds)
            async with session_factory() as session:
                renewed = await renew_running_job_lease(
                    session,
                    AiPageMutationJob,
                    job_id=database_id,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning(
                "AI 页面变更任务续租失败，旧 Worker 将停止提交结果。",
                exc_info=True,
                extra={"event": "ai.page_mutation.job.heartbeat_failed", "job_id": database_id},
            )
            lease_lost.set()
            return
        if not renewed:
            lease_lost.set()
            return


async def _retry_or_fail_job(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
    code: str,
    message: str,
) -> None:
    """基础设施错误在租约拥有者条件下重排，达到上限后收敛失败。"""

    async with session_factory() as session:
        job = await session.get(AiPageMutationJob, database_id)
        if job is None or job.status != "running" or job.worker_id != worker_id:
            return
        now = utc_now()
        if job.cancel_requested_at is not None:
            # 取消请求优先于晚到的 Runtime/浏览器错误；不能把取消任务覆盖成失败。
            transitioned = await transition_owned_running_job(
                session,
                AiPageMutationJob,
                job_id=database_id,
                worker_id=worker_id,
                values=_cancelled_job_transition_values(
                    now=now,
                    cancel_requested_at=job.cancel_requested_at,
                ),
                require_active_lease=True,
                commit=False,
            )
            if transitioned:
                await session.refresh(job)
                await sync_external_task_from_domain_job(session, job=job)
                await session.commit()
            else:
                await session.rollback()
            return
        if job.attempt_count < _MAX_ATTEMPTS:
            values = {
                "status": "pending",
                "worker_id": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "started_at": None,
                "error_code": code,
                "error_message": message,
            }
        else:
            values = {
                "status": "failed",
                "worker_id": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "finished_at": now,
                "error_code": code,
                "error_message": message,
            }
        transitioned = await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values=values,
            # 查询完成后到状态流转前可能收到取消；条件更新确保不会反向覆盖它。
            require_not_cancelled=True,
            require_active_lease=True,
            commit=False,
        )
        if transitioned:
            await session.refresh(job)
            await sync_external_task_from_domain_job(session, job=job)
            await session.commit()
        else:
            await session.rollback()


async def _transition_job_failed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
    code: str,
    message: str,
) -> None:
    """把权限或安全错误直接收敛为失败，不执行基础设施重试。"""

    async with session_factory() as session:
        job = await session.get(AiPageMutationJob, database_id)
        if job is None or job.status != "running" or job.worker_id != worker_id:
            return
        now = utc_now()
        if job.cancel_requested_at is not None:
            # 取消与权限校验失败并发时，用户的取消语义优先。
            transitioned = await transition_owned_running_job(
                session,
                AiPageMutationJob,
                job_id=database_id,
                worker_id=worker_id,
                values=_cancelled_job_transition_values(
                    now=now,
                    cancel_requested_at=job.cancel_requested_at,
                ),
                require_active_lease=True,
                commit=False,
            )
            if transitioned:
                await session.refresh(job)
                await sync_external_task_from_domain_job(session, job=job)
                await session.commit()
            else:
                await session.rollback()
            return
        transitioned = await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values={
                "status": "failed",
                "worker_id": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "finished_at": now,
                "error_code": code,
                "error_message": message,
            },
            require_not_cancelled=True,
            require_active_lease=True,
            commit=False,
        )
        if transitioned:
            await session.refresh(job)
            await sync_external_task_from_domain_job(session, job=job)
            await session.commit()
        else:
            await session.rollback()


async def _transition_job_cancelled(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
) -> None:
    """在拥有者条件下取消正在执行的任务。"""

    async with session_factory() as session:
        now = utc_now()
        transitioned = await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values=_cancelled_job_transition_values(now=now),
            require_active_lease=True,
            commit=False,
        )
        if transitioned:
            job = await session.get(AiPageMutationJob, database_id)
            if job is not None:
                await sync_external_task_from_domain_job(session, job=job)
            await session.commit()
        else:
            await session.rollback()


async def _transition_cancel_requested_job_if_owned(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
) -> bool:
    """仅由仍持有租约的 Worker 收敛已请求取消的运行中 Job。"""

    async with session_factory() as session:
        job = await session.scalar(
            select(AiPageMutationJob).where(
                AiPageMutationJob.id == database_id,
                AiPageMutationJob.status == "running",
                AiPageMutationJob.worker_id == worker_id,
                AiPageMutationJob.cancel_requested_at.is_not(None),
            )
        )
        if job is None:
            return False
        transitioned = await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values=_cancelled_job_transition_values(
                now=utc_now(),
                cancel_requested_at=job.cancel_requested_at,
            ),
            require_active_lease=True,
            commit=False,
        )
        if transitioned:
            await session.refresh(job)
            await sync_external_task_from_domain_job(session, job=job)
            await session.commit()
        else:
            await session.rollback()
        return transitioned


async def _reconcile_cancelled_and_orphaned_jobs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """传播 run 取消/终态，但不提前释放运行中 Job 的租约。"""

    now = utc_now()
    async with session_factory() as session:
        terminal_statuses = ("completed", "cancelled", "failed")
        orphaned_pending_job_ids = list(
            (
                await session.scalars(
                    select(AiPageMutationJob.id)
                    .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationJob.run_id)
                    .where(
                        AiPageMutationJob.status == "pending",
                        AiAgentRun.status.in_(terminal_statuses),
                    )
                    .limit(128)
                )
            ).all()
        )
        orphaned_running_job_ids = list(
            (
                await session.scalars(
                    select(AiPageMutationJob.id)
                    .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationJob.run_id)
                    .where(
                        AiPageMutationJob.status == "running",
                        AiPageMutationJob.cancel_requested_at.is_(None),
                        AiAgentRun.status.in_(terminal_statuses),
                    )
                    .limit(128)
                )
            ).all()
        )
        orphaned_pending_batch_ids = list(
            (
                await session.scalars(
                    select(AiPageMutationBatch.batch_id)
                    .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationBatch.run_id)
                    .where(
                        AiPageMutationBatch.status == "pending",
                        AiAgentRun.status.in_(terminal_statuses),
                    )
                    .limit(128)
                )
            ).all()
        )
        if orphaned_pending_job_ids:
            await session.execute(
                update(AiPageMutationJob)
                .where(
                    AiPageMutationJob.id.in_(orphaned_pending_job_ids),
                    AiPageMutationJob.status == "pending",
                )
                .values(
                    status="cancelled",
                    cancel_requested_at=now,
                    finished_at=now,
                    error_code="AI_RUN_NOT_ACTIVE",
                    error_message="智能体运行已结束。",
                )
            )
        if orphaned_running_job_ids:
            # 正在 Runtime/Chromium 中运行的 Job 只能请求取消；实际执行者会在
            # 最终写页面前的安全边界收敛状态并释放自身租约。
            await session.execute(
                update(AiPageMutationJob)
                .where(
                    AiPageMutationJob.id.in_(orphaned_running_job_ids),
                    AiPageMutationJob.status == "running",
                    AiPageMutationJob.cancel_requested_at.is_(None),
                )
                .values(cancel_requested_at=now)
                .execution_options(synchronize_session=False)
            )
        if orphaned_pending_batch_ids:
            # 页面 Batch 只负责分组；续跑与 Requirement 由统一 external 状态机管理。
            await session.execute(
                update(AiPageMutationBatch)
                .where(
                    AiPageMutationBatch.batch_id.in_(orphaned_pending_batch_ids),
                    AiPageMutationBatch.status == "pending",
                )
                .values(
                    status="cancelled",
                    worker_id=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    finished_at=now,
                    error_code="AI_RUN_NOT_ACTIVE",
                    error_message="智能体运行已结束。",
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
        if orphaned_pending_job_ids or orphaned_running_job_ids or orphaned_pending_batch_ids:
            for job_id in (*orphaned_pending_job_ids,):
                job = await session.get(AiPageMutationJob, int(job_id))
                if job is not None:
                    await sync_external_task_from_domain_job(session, job=job)
            await session.commit()
        cancelling_runs = list(
            (
                await session.scalars(
                    select(AiAgentRun.run_id).where(
                        AiAgentRun.status.in_(("cancelling", "waiting_external")),
                        AiAgentRun.cancel_requested_at.is_not(None),
                    )
                )
            ).all()
        )
    for run_id in cancelling_runs:
        async with session_factory() as session:
            current_run = await session.scalar(
                select(AiAgentRun)
                .where(
                    AiAgentRun.run_id == run_id,
                    AiAgentRun.status.in_(("cancelling", "waiting_external")),
                    AiAgentRun.cancel_requested_at.is_not(None),
                )
                .with_for_update()
            )
            if current_run is None:
                continue
            cancel_requested_at = current_run.cancel_requested_at or now
            await session.execute(
                update(AiPageMutationJob)
                .where(
                    AiPageMutationJob.run_id == current_run.run_id,
                    AiPageMutationJob.status == "pending",
                )
                .values(
                    cancel_requested_at=cancel_requested_at,
                    status="cancelled",
                    worker_id=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    finished_at=now,
                    error_code="AI_RUN_CANCELLED",
                    error_message="智能体运行已取消。",
                )
                .execution_options(synchronize_session=False)
            )
            await session.execute(
                update(AiPageMutationJob)
                .where(
                    AiPageMutationJob.run_id == current_run.run_id,
                    AiPageMutationJob.status == "running",
                    AiPageMutationJob.cancel_requested_at.is_(None),
                )
                .values(cancel_requested_at=cancel_requested_at)
                .execution_options(synchronize_session=False)
            )
            await session.execute(
                update(AiPageMutationBatch)
                .where(
                    AiPageMutationBatch.run_id == current_run.run_id,
                    AiPageMutationBatch.status == "pending",
                )
                .values(
                    status="cancelled",
                    worker_id=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    finished_at=now,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            cancelled_jobs = list(
                (
                    await session.scalars(
                        select(AiPageMutationJob).where(AiPageMutationJob.run_id == current_run.run_id)
                    )
                ).all()
            )
            for job in cancelled_jobs:
                await sync_external_task_from_domain_job(session, job=job)
            await PlatformAgentRuntimeStore(session, user_id=current_run.user_id).mark_terminal(
                current_run,
                status="cancelled",
                content="用户停止了当前页面变更运行。",
            )


def _is_fatal_job_error(code: str | None) -> bool:
    """判断任务错误是否表示权限或安全边界已经失效。"""

    normalized = str(code or "")
    return (
        normalized.startswith("AUTH_")
        or normalized.endswith("_ACCESS_DENIED")
        or normalized in {
            "AI_TOOL_CONTEXT_MISMATCH",
            "AI_TOOL_SCOPE_DENIED",
            "AI_PAGE_SCOPE_DENIED",
            "PAGE_SCOPE_DENIED",
        }
    )


def _is_permission_denied_error(error: AppException) -> bool:
    """识别必须终止整个 Batch 的认证、授权和访问拒绝错误。"""

    normalized = str(error.code or "")
    return error.status_code in {401, 403} or normalized.endswith("_ACCESS_DENIED")


def _is_retryable_infrastructure_error(error: AppException) -> bool:
    """识别即使返回 429 也应由后台重排的 Runtime 容量与排队错误。"""

    return error.status_code >= 500 or str(error.code or "") in _RETRYABLE_RUNTIME_QUEUE_ERROR_CODES


def _fatal_permission_error_code(code: str | None) -> str:
    """保留已知权限错误，否则编码为 AUTH 前缀以供 Batch 终止判断。"""

    normalized = str(code or "").strip()
    if _is_fatal_job_error(normalized):
        return normalized
    suffix = normalized or "UNKNOWN"
    return f"{_FATAL_PERMISSION_ERROR_PREFIX}:{suffix}"[:128]


def _cancelled_job_transition_values(
    *,
    now: datetime,
    cancel_requested_at: datetime | None = None,
) -> dict[str, object]:
    """构造取消终态字段，保证所有取消路径输出一致的任务状态。"""

    return {
        "status": "cancelled",
        "worker_id": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "cancel_requested_at": cancel_requested_at or now,
        "finished_at": now,
        "error_code": "AI_RUN_CANCELLED",
        "error_message": "智能体运行已取消。",
    }


def _display_tool_name(operation: str) -> str:
    """将内部页面任务操作还原为前端可关联的 AI 工具名。"""

    return {
        "create_page": "create_project_page",
        "apply_page_edits": "apply_page_edits",
    }.get(operation, operation)
