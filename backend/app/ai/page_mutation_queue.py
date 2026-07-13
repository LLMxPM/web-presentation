"""文件功能：运行 AI 页面变更持久化队列、租约心跳、取消协调与模型自动续跑。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI
from pydantic_ai import DeferredToolResults
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.page_mutation_executor import AiPageMutationExecutor
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.platform_tools import recoverable_tool_error_result
from app.ai.run_write_fence import AgentRunWriteFenceLost, PageMutationContinuationWriteFence
from app.ai.session_facade_pydantic import AgentSessionFacade
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun
from app.models.ai_page_mutation import AiPageMutationBatch, AiPageMutationJob
from app.models.enums import RecordStatus
from app.models.user import User
from app.schemas.agent import AgentRunEvent
from app.services.auth_service import AuthContext
from app.services.durable_job_lease_service import (
    claim_pending_jobs,
    recover_expired_running_jobs,
    renew_running_job_lease,
    transition_owned_running_job,
)

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
_FATAL_PERMISSION_ERROR_PREFIX = "AUTH_PERMISSION_DENIED"
_RETRYABLE_RUNTIME_QUEUE_ERROR_CODES = {"RUNTIME_VITE_QUEUE_FULL", "RUNTIME_VITE_QUEUE_TIMEOUT"}


class _ContinuationLeaseLost(RuntimeError):
    """表示自动续跑已失去 Batch 租约，旧协调器不得继续调用模型。"""


@dataclass(frozen=True, slots=True)
class _ClaimedContinuationBatch:
    """保存一次条件认领得到的 Batch 业务 ID 与不可复用租约代次。"""

    batch_id: str
    lease_generation: int


async def run_ai_page_mutation_queue_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
) -> None:
    """启动配置数量的页面变更 Worker 和单个自动续跑协调器。"""

    settings = get_settings()
    concurrency = max(1, int(getattr(settings, "ai_page_mutation_concurrency", 1)))
    workers = [
        asyncio.create_task(
            _run_job_worker(session_factory, worker_id=f"ai-page-job-{uuid4().hex[:12]}"),
            name=f"ai-page-mutation-worker-{index + 1}",
        )
        for index in range(concurrency)
    ]
    coordinator = asyncio.create_task(
        _run_continuation_coordinator(
            session_factory,
            app=app,
            worker_id=f"ai-page-continuation-{uuid4().hex[:12]}",
        ),
        name="ai-page-mutation-continuation",
    )
    try:
        await asyncio.gather(*workers, coordinator)
    finally:
        for task in (*workers, coordinator):
            task.cancel()
        for task in (*workers, coordinator):
            with suppress(asyncio.CancelledError):
                await task


async def recover_interrupted_ai_page_mutation_jobs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """恢复过期任务和续跑租约；仍有效的其他实例任务保持不变。"""

    async with session_factory() as session:
        summary = await recover_expired_running_jobs(
            session,
            AiPageMutationJob,
            max_attempts=_MAX_ATTEMPTS,
            interrupted_error_code="AI_PAGE_MUTATION_INTERRUPTED",
            interrupted_error_message="页面变更任务执行中断且已达到最大重试次数。",
        )
    recovered_batches = await _recover_expired_continuation_batches(session_factory)
    total = summary.total_count + recovered_batches
    if total:
        logger.warning(
            "恢复了中断的 AI 页面变更任务。",
            extra={"event": "ai.page_mutation.recovered", "count": total},
        )
    return total


async def _recover_expired_continuation_batches(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """恢复过期的模型续跑租约，并把中断的 run 还原为可继续的等待态。"""

    now = utc_now()
    terminal_statuses = {"completed", "cancelled", "failed"}
    recovered = 0
    async with session_factory() as session:
        batches = list(
            (
                await session.scalars(
                    select(AiPageMutationBatch)
                    .where(
                        AiPageMutationBatch.status == "resuming",
                        (AiPageMutationBatch.lease_expires_at.is_(None))
                        | (AiPageMutationBatch.lease_expires_at <= now),
                    )
                    .order_by(AiPageMutationBatch.created_at.asc())
                )
            ).all()
        )
        for batch in batches:
            # 先通过代次 CAS 使旧协调器失去围栏，再决定恢复/终止状态。不能在
            # 已过期记录上直接修改 ORM 对象，否则旧实例可能与恢复者并发回写。
            if not await _take_expired_batch_for_recovery(session, batch=batch, now=now):
                continue
            run = await session.get(AiAgentRun, batch.run_id)
            if run is None:
                _mark_recovered_batch_terminal(
                    batch,
                    status="failed",
                    now=now,
                    code="AI_RUN_NOT_FOUND",
                    message="待恢复运行不存在。",
                )
                recovered += 1
                continue
            if run.cancel_requested_at is not None or run.status == "cancelling":
                _mark_recovered_batch_terminal(batch, status="cancelled", now=now)
                recovered += 1
                continue
            if run.status in terminal_statuses:
                _mark_recovered_batch_terminal(
                    batch,
                    status="completed" if run.status == "completed" else run.status,
                    now=now,
                    code=run.error_code,
                    message=run.error_message,
                )
                recovered += 1
                continue

            requirement = await _load_batch_requirement(session, batch=batch)
            if requirement is None:
                _mark_recovered_batch_terminal(
                    batch,
                    status="failed",
                    now=now,
                    code="AI_EXTERNAL_REQUIREMENT_MISSING",
                    message="页面变更批次缺少可恢复的外部 requirement。",
                )
                run.status = "failed"
                run.pending_requirement_json = None
                run.error_code = "AI_EXTERNAL_REQUIREMENT_MISSING"
                run.error_message = "页面变更批次缺少可恢复的外部 requirement。"
                run.finished_at = now
                recovered += 1
                continue

            pending_requirement = await session.scalar(
                select(AiAgentRequirement)
                .where(
                    AiAgentRequirement.run_id == run.run_id,
                    AiAgentRequirement.kind == "external_job",
                    AiAgentRequirement.status == "pending",
                )
                .order_by(AiAgentRequirement.created_at.desc())
                .limit(1)
            )
            # 已产生下一轮 external requirement 时，当前 Batch 的结果已经回灌模型；
            # 只能补齐旧 Batch 终态，不能把 run 倒退回上一轮等待。
            if (
                run.status == "waiting_external"
                and pending_requirement is not None
                and batch.requirement_id
                and pending_requirement.requirement_id != batch.requirement_id
            ):
                _mark_recovered_batch_terminal(batch, status="completed", now=now)
                recovered += 1
                continue

            run.status = "waiting_external"
            run.pending_requirement_json = dict(requirement.payload_json or {})
            run.error_code = None
            run.error_message = None
            _requeue_recovered_batch(batch, now=now)
            recovered += 1
        await session.commit()
    return recovered


async def _take_expired_batch_for_recovery(
    session: AsyncSession,
    *,
    batch: AiPageMutationBatch,
    now: datetime,
) -> bool:
    """以租约代次 CAS 认领一个过期续跑 Batch，成功后旧协调器无法继续提交。"""

    expired = (AiPageMutationBatch.lease_expires_at.is_(None)) | (AiPageMutationBatch.lease_expires_at <= now)
    result = await session.execute(
        update(AiPageMutationBatch)
        .where(
            AiPageMutationBatch.batch_id == batch.batch_id,
            AiPageMutationBatch.status == "resuming",
            AiPageMutationBatch.lease_generation == batch.lease_generation,
            expired,
        )
        .values(
            worker_id=None,
            lease_expires_at=None,
            heartbeat_at=None,
            lease_generation=batch.lease_generation + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        return False
    await session.refresh(batch)
    return True


async def _load_batch_requirement(
    session: AsyncSession,
    *,
    batch: AiPageMutationBatch,
) -> AiAgentRequirement | None:
    """读取 Batch 绑定的 requirement；兼容尚未写入 requirement_id 就崩溃的旧记录。"""

    if batch.requirement_id:
        requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == batch.requirement_id)
        )
        if requirement is not None:
            return requirement
    return await session.scalar(
        select(AiAgentRequirement)
        .where(
            AiAgentRequirement.run_id == batch.run_id,
            AiAgentRequirement.kind == "external_job",
            AiAgentRequirement.status.in_(("pending", "resolved")),
        )
        .order_by(AiAgentRequirement.created_at.desc())
        .limit(1)
    )


def _requeue_recovered_batch(batch: AiPageMutationBatch, *, now: datetime) -> None:
    """清除过期续跑租约并重新暴露给协调器。"""

    batch.status = "pending"
    batch.worker_id = None
    batch.lease_expires_at = None
    batch.heartbeat_at = None
    batch.started_at = None
    batch.error_code = None
    batch.error_message = None
    batch.finished_at = None
    batch.updated_at = now


def _mark_recovered_batch_terminal(
    batch: AiPageMutationBatch,
    *,
    status: str,
    now: datetime,
    code: str | None = None,
    message: str | None = None,
) -> None:
    """在恢复时收敛已经无需再次续跑的 Batch。"""

    batch.status = status
    batch.worker_id = None
    batch.lease_expires_at = None
    batch.heartbeat_at = None
    batch.finished_at = now
    batch.error_code = code
    batch.error_message = message
    batch.updated_at = now


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
    while True:
        try:
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
                await asyncio.sleep(poll_interval)
                continue
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
        logger.info(
            "AI 页面变更任务本次执行结束。",
            extra={
                "event": "ai.page_mutation.job.execution_finished",
                "job_id": database_id,
                "worker_id": worker_id,
                "duration_ms": round((monotonic() - execution_started_at) * 1000, 2),
            },
        )


async def _run_continuation_coordinator(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
    worker_id: str,
) -> None:
    """等待 Batch 全部完成，然后一次性向模型回灌所有 deferred results。"""

    settings = get_settings()
    poll_interval = max(0.05, float(getattr(settings, "ai_page_mutation_poll_interval_seconds", 0.5)))
    recovery_interval = max(1.0, min(float(getattr(settings, "durable_job_heartbeat_seconds", 30)), 30.0))
    last_recovery_at = 0.0
    while True:
        try:
            if monotonic() - last_recovery_at >= recovery_interval:
                await recover_interrupted_ai_page_mutation_jobs_on_startup(session_factory)
                last_recovery_at = monotonic()
            await _reconcile_cancelled_and_orphaned_jobs(session_factory)
            claimed_batch = await _claim_ready_batch(session_factory, worker_id=worker_id)
            if claimed_batch is None:
                await asyncio.sleep(poll_interval)
                continue
            await _continue_claimed_batch(
                session_factory,
                app=app,
                batch_id=claimed_batch.batch_id,
                lease_generation=claimed_batch.lease_generation,
                worker_id=worker_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("AI 页面变更续跑协调器异常。", extra={"event": "ai.page_mutation.coordinator.failed"})
            await asyncio.sleep(poll_interval)


async def _claim_ready_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    worker_id: str,
) -> _ClaimedContinuationBatch | None:
    """查找全部 Job 已终态且 run 正在等待的 Batch，并用条件更新认领。"""

    now = utc_now()
    lease_seconds = max(1, int(getattr(get_settings(), "durable_job_lease_seconds", 300)))
    async with session_factory() as session:
        candidates = list(
            (
                await session.scalars(
                    select(AiPageMutationBatch)
                    .join(AiAgentRun, AiAgentRun.run_id == AiPageMutationBatch.run_id)
                    .where(
                        AiPageMutationBatch.status == "pending",
                        AiAgentRun.status == "waiting_external",
                        AiAgentRun.cancel_requested_at.is_(None),
                    )
                    .order_by(AiPageMutationBatch.created_at.asc())
                    .limit(8)
                )
            ).all()
        )
    for batch in candidates:
        async with session_factory() as session:
            nonterminal_count = int(
                await session.scalar(
                    select(func.count(AiPageMutationJob.id)).where(
                        AiPageMutationJob.batch_id == batch.batch_id,
                        AiPageMutationJob.status.not_in(_TERMINAL_JOB_STATUSES),
                    )
                )
                or 0
            )
            total_count = int(
                await session.scalar(
                    select(func.count(AiPageMutationJob.id)).where(AiPageMutationJob.batch_id == batch.batch_id)
                )
                or 0
            )
            if nonterminal_count or total_count == 0:
                continue
            # 计数查询只用于候选筛选；开始条件写前释放 SQLite 只读事务。
            await session.rollback()
            claim = await session.execute(
                update(AiPageMutationBatch)
                .where(
                    AiPageMutationBatch.batch_id == batch.batch_id,
                    AiPageMutationBatch.status == "pending",
                    AiPageMutationBatch.lease_generation == batch.lease_generation,
                )
                .values(
                    status="resuming",
                    worker_id=worker_id,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    heartbeat_at=now,
                    started_at=now,
                    lease_generation=batch.lease_generation + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            if int(claim.rowcount or 0) == 1:
                return _ClaimedContinuationBatch(
                    batch_id=batch.batch_id,
                    lease_generation=batch.lease_generation + 1,
                )
    return None


async def _continue_claimed_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
    batch_id: str,
    lease_generation: int,
    worker_id: str,
) -> None:
    """构造多 call DeferredToolResults，并通过后台 AuthContext 自动恢复模型。"""

    fence = PageMutationContinuationWriteFence(
        batch_id=batch_id,
        worker_id=worker_id,
        lease_generation=lease_generation,
    )
    lease_lost = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_batch_lease(
            session_factory,
            batch_id=batch_id,
            worker_id=worker_id,
            lease_generation=lease_generation,
            lease_lost=lease_lost,
        ),
        name=f"ai-page-batch-heartbeat-{batch_id}",
    )
    continuation_task: asyncio.Task[str] | None = None
    lease_waiter: asyncio.Task[bool] | None = None
    try:
        async with session_factory() as session:
            batch = await session.scalar(
                select(AiPageMutationBatch).where(*fence.batch_conditions(utc_now()))
            )
            if batch is None:
                return
            run = await session.get(AiAgentRun, batch.run_id)
            jobs = list(
                (
                    await session.scalars(
                        select(AiPageMutationJob)
                        .where(AiPageMutationJob.batch_id == batch_id)
                        .order_by(AiPageMutationJob.created_at.asc(), AiPageMutationJob.id.asc())
                    )
                ).all()
            )
            if run is None:
                await _mark_batch_failed_in_session(
                    session,
                    batch,
                    fence=fence,
                    code="AI_RUN_NOT_FOUND",
                    message="待恢复运行不存在。",
                )
                return
            if run.cancel_requested_at is not None or any(job.status == "cancelled" for job in jobs):
                await _cancel_waiting_run(session, run=run, batch=batch, fence=fence)
                return
            fatal_job = next(
                (job for job in jobs if job.status == "failed" and _is_fatal_job_error(job.error_code)),
                None,
            )
            if fatal_job is not None:
                await _fail_waiting_run(
                    session,
                    run=run,
                    batch=batch,
                    fence=fence,
                    code=fatal_job.error_code or "AI_PAGE_MUTATION_FORBIDDEN",
                    message=fatal_job.error_message or "页面变更权限已失效。",
                )
                return
            user = await session.get(User, run.user_id)
            if user is None or user.status != RecordStatus.ACTIVE.value:
                await _fail_waiting_run(
                    session,
                    run=run,
                    batch=batch,
                    fence=fence,
                    code="AUTH_DISABLED",
                    message="执行页面变更的用户已被禁用或删除。",
                )
                return
            deferred_results = DeferredToolResults()
            for job in jobs:
                if job.status == "succeeded":
                    deferred_results.calls[job.tool_call_id] = job.result_json
                else:
                    deferred_results.calls[job.tool_call_id] = recoverable_tool_error_result(
                        code=job.error_code or "AI_PAGE_MUTATION_FAILED",
                        message=job.error_message or "页面变更任务执行失败。",
                        status_code=503,
                        hint="该任务已停止重试，请根据错误信息重新调用。",
                    )
            current = AuthContext(
                user=user,
                session_token="",
                backend_session_id=f"background:{run.run_id}",
            )
            requirement_id = await _pending_external_requirement_id(session, run.run_id)
            await fence.ensure_owned(session, now=utc_now())
            batch.requirement_id = requirement_id
            await session.commit()

        if not await _owns_active_continuation_lease(
            session_factory,
            batch_id=batch_id,
            worker_id=worker_id,
            lease_generation=lease_generation,
        ):
            raise _ContinuationLeaseLost()
        continuation_task = asyncio.create_task(
            _continue_external_batch_to_store(
                session_factory,
                app=app,
                current=current,
                run_id=run.run_id,
                deferred_results=deferred_results,
                continuation_fence=fence,
            )
        )
        lease_waiter = asyncio.create_task(lease_lost.wait())
        completed, _ = await asyncio.wait(
            {continuation_task, lease_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lease_waiter in completed:
            if not continuation_task.done():
                continuation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await continuation_task
            raise _ContinuationLeaseLost()
        status = await continuation_task
        if lease_lost.is_set():
            raise _ContinuationLeaseLost()

        async with session_factory() as session:
            now = utc_now()
            completed = await session.execute(
                update(AiPageMutationBatch)
                .where(
                    *fence.batch_conditions(now),
                    _batch_run_has_no_cancellation_request(),
                )
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
            if int(completed.rowcount or 0) != 1:
                await session.rollback()
                if await _mark_claimed_batch_cancelled_if_requested(
                    session_factory,
                    batch_id=batch_id,
                    worker_id=worker_id,
                    lease_generation=lease_generation,
                ):
                    return
                raise _ContinuationLeaseLost()
            # 结果已经进入 Pydantic AI message history，清理 Job 副本避免长期重复保存大诊断对象。
            await session.execute(
                update(AiPageMutationJob)
                .where(AiPageMutationJob.batch_id == batch_id)
                .values(result_json=None)
            )
            await session.commit()
            logger.info(
                "AI 页面变更批次已自动恢复模型。",
                extra={"event": "ai.page_mutation.continued", "batch_id": batch_id, "run_status": status},
            )
    except (AgentRunWriteFenceLost, _ContinuationLeaseLost):
        logger.warning(
            "AI 页面变更续跑已失去租约，旧协调器停止执行。",
            extra={"event": "ai.page_mutation.continue_lease_lost", "batch_id": batch_id},
        )
    except asyncio.CancelledError:
        if continuation_task is not None and not continuation_task.done():
            continuation_task.cancel()
            with suppress(asyncio.CancelledError):
                await continuation_task
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "AI 页面变更批次自动续跑失败。",
            extra={"event": "ai.page_mutation.continue_failed", "batch_id": batch_id},
        )
        await _fail_claimed_batch(
            session_factory,
            batch_id=batch_id,
            worker_id=worker_id,
            lease_generation=lease_generation,
            code="AI_PAGE_MUTATION_CONTINUE_FAILED",
            message=str(exc)[:2000] or "页面变更完成，但自动恢复模型失败。",
        )
    finally:
        if lease_waiter is not None and not lease_waiter.done():
            lease_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await lease_waiter
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _continue_external_batch_to_store(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
    current: AuthContext,
    run_id: str,
    deferred_results: DeferredToolResults,
    continuation_fence: PageMutationContinuationWriteFence,
) -> str:
    """在独立短会话中执行一次被租约保护的 Pydantic AI 自动续跑。"""

    async with session_factory() as session:
        return await AgentSessionFacade(app=app, current=current, session=session).continue_external_page_mutations_to_store(
            run_id=run_id,
            deferred_results=deferred_results,
            continuation_fence=continuation_fence,
        )


async def _owns_active_continuation_lease(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_id: str,
    worker_id: str,
    lease_generation: int,
) -> bool:
    """在调用模型前再次核对 Batch 所有者与未过期租约，形成续跑栅栏。"""

    fence = PageMutationContinuationWriteFence(
        batch_id=batch_id,
        worker_id=worker_id,
        lease_generation=lease_generation,
    )
    async with session_factory() as session:
        return await fence.is_owned(session, now=utc_now())


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


async def _heartbeat_batch_lease(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_id: str,
    worker_id: str,
    lease_generation: int,
    lease_lost: asyncio.Event,
) -> None:
    """续租模型恢复 Batch；续租失败时通知调用方取消旧协调器的模型执行。"""

    settings = get_settings()
    heartbeat_seconds = max(1, int(getattr(settings, "durable_job_heartbeat_seconds", 30)))
    lease_seconds = max(heartbeat_seconds + 1, int(getattr(settings, "durable_job_lease_seconds", 300)))
    while True:
        try:
            await asyncio.sleep(heartbeat_seconds)
            now = utc_now()
            async with session_factory() as session:
                result = await session.execute(
                    update(AiPageMutationBatch)
                    .where(
                        *PageMutationContinuationWriteFence(
                            batch_id=batch_id,
                            worker_id=worker_id,
                            lease_generation=lease_generation,
                        ).batch_conditions(now)
                    )
                    .values(
                        heartbeat_at=now,
                        lease_expires_at=now + timedelta(seconds=lease_seconds),
                    )
                    .execution_options(synchronize_session=False)
                )
                await session.commit()
            if int(result.rowcount or 0) != 1:
                lease_lost.set()
                return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning(
                "AI 页面变更 Batch 续租失败，旧协调器将停止续跑。",
                exc_info=True,
                extra={"event": "ai.page_mutation.continuation_heartbeat_failed", "batch_id": batch_id},
            )
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
            await transition_owned_running_job(
                session,
                AiPageMutationJob,
                job_id=database_id,
                worker_id=worker_id,
                values=_cancelled_job_transition_values(
                    now=now,
                    cancel_requested_at=job.cancel_requested_at,
                ),
                require_active_lease=True,
            )
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
        await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values=values,
            # 查询完成后到状态流转前可能收到取消；条件更新确保不会反向覆盖它。
            require_not_cancelled=True,
            require_active_lease=True,
        )


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
            await transition_owned_running_job(
                session,
                AiPageMutationJob,
                job_id=database_id,
                worker_id=worker_id,
                values=_cancelled_job_transition_values(
                    now=now,
                    cancel_requested_at=job.cancel_requested_at,
                ),
                require_active_lease=True,
            )
            return
        await transition_owned_running_job(
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
        )


async def _transition_job_cancelled(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
) -> None:
    """在拥有者条件下取消正在执行的任务。"""

    async with session_factory() as session:
        now = utc_now()
        await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values=_cancelled_job_transition_values(now=now),
            require_active_lease=True,
        )


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
        return await transition_owned_running_job(
            session,
            AiPageMutationJob,
            job_id=database_id,
            worker_id=worker_id,
            values=_cancelled_job_transition_values(
                now=utc_now(),
                cancel_requested_at=job.cancel_requested_at,
            ),
            require_active_lease=True,
        )


def _batch_run_has_no_cancellation_request():
    """构造关联条件：只有 run 未收到取消请求时，Batch 才可标记完成。"""

    return (
        select(AiAgentRun.run_id)
        .where(
            AiAgentRun.run_id == AiPageMutationBatch.run_id,
            AiAgentRun.cancel_requested_at.is_(None),
        )
        .exists()
    )


async def _mark_claimed_batch_cancelled_if_requested(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_id: str,
    worker_id: str,
    lease_generation: int,
) -> bool:
    """由续跑租约拥有者在模型调用返回后收敛已取消的 Batch。"""

    now = utc_now()
    fence = PageMutationContinuationWriteFence(
        batch_id=batch_id,
        worker_id=worker_id,
        lease_generation=lease_generation,
    )
    cancellation_requested = (
        select(AiAgentRun.run_id)
        .where(
            AiAgentRun.run_id == AiPageMutationBatch.run_id,
            AiAgentRun.cancel_requested_at.is_not(None),
        )
        .exists()
    )
    async with session_factory() as session:
        result = await session.execute(
            update(AiPageMutationBatch)
            .where(*fence.batch_conditions(now), cancellation_requested)
            .values(
                status="cancelled",
                finished_at=now,
                worker_id=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) != 1:
            await session.rollback()
            return False
        await session.commit()
        return True


async def _reconcile_cancelled_and_orphaned_jobs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """传播 run 取消/终态，但不提前释放运行中 Job 或续跑 Batch 的租约。"""

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
            # pending Batch 没有协调器所有者，可以直接结束；resuming Batch 必须
            # 留给当前租约拥有者完成收尾，不能由巡检任务抢先释放租约。
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
        if orphaned_pending_job_ids or orphaned_running_job_ids or orphaned_pending_batch_ids:
            await session.commit()
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
            # resuming Batch 的 worker_id/lease 字段刻意不在此处修改。运行中的
            # 模型续跑会通过 run.cancel_requested_at 感知取消，并由租约拥有者在
            # 真实停止后完成 Batch 终态迁移。
            await PlatformAgentRuntimeStore(session, user_id=current_run.user_id).mark_terminal(
                current_run,
                status="cancelled",
                content="用户停止了当前页面变更运行。",
            )


async def _pending_external_requirement_id(session: AsyncSession, run_id: str) -> str | None:
    """读取 Batch 对应的 pending external requirement 业务 ID。"""

    requirement = await session.scalar(
        select(AiAgentRequirement)
        .where(
            AiAgentRequirement.run_id == run_id,
            AiAgentRequirement.status == "pending",
            AiAgentRequirement.kind == "external_job",
        )
        .order_by(AiAgentRequirement.created_at.desc())
    )
    return requirement.requirement_id if requirement is not None else None


async def _mark_batch_failed_in_session(
    session: AsyncSession,
    batch: AiPageMutationBatch,
    *,
    fence: PageMutationContinuationWriteFence | None = None,
    code: str,
    message: str,
) -> None:
    """在当前短事务中收敛无法恢复的 Batch。"""

    now = utc_now()
    if fence is not None:
        await fence.ensure_owned(session, now=now)
    batch.status = "failed"
    batch.error_code = code
    batch.error_message = message
    batch.finished_at = now
    batch.worker_id = None
    batch.lease_expires_at = None
    batch.heartbeat_at = None
    batch.updated_at = now
    await session.commit()


async def _cancel_waiting_run(
    session: AsyncSession,
    *,
    run: AiAgentRun,
    batch: AiPageMutationBatch,
    fence: PageMutationContinuationWriteFence | None = None,
) -> None:
    """批次被取消时同步终止 waiting_external run。"""

    await PlatformAgentRuntimeStore(
        session,
        user_id=run.user_id,
        write_fence=fence,
    ).mark_terminal(
        run,
        status="cancelled",
        content="页面变更任务已取消。",
    )
    now = utc_now()
    if fence is not None:
        await fence.ensure_owned(session, now=now)
    batch.status = "cancelled"
    batch.finished_at = now
    batch.worker_id = None
    batch.lease_expires_at = None
    batch.heartbeat_at = None
    batch.updated_at = now
    await session.commit()


async def _fail_waiting_run(
    session: AsyncSession,
    *,
    run: AiAgentRun,
    batch: AiPageMutationBatch,
    fence: PageMutationContinuationWriteFence | None = None,
    code: str,
    message: str,
) -> None:
    """权限等致命错误同时终止 Batch 与 run。"""

    await PlatformAgentRuntimeStore(
        session,
        user_id=run.user_id,
        write_fence=fence,
    ).mark_terminal(
        run,
        status="failed",
        error_code=code,
        error_message=message,
    )
    now = utc_now()
    if fence is not None:
        await fence.ensure_owned(session, now=now)
    batch.status = "failed"
    batch.error_code = code
    batch.error_message = message
    batch.finished_at = now
    batch.worker_id = None
    batch.lease_expires_at = None
    batch.heartbeat_at = None
    batch.updated_at = now
    await session.commit()


async def _fail_claimed_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_id: str,
    worker_id: str,
    lease_generation: int,
    code: str,
    message: str,
) -> None:
    """自动续跑异常时只允许租约拥有者收敛 Batch，并终止仍在等待的 run。"""

    fence = PageMutationContinuationWriteFence(
        batch_id=batch_id,
        worker_id=worker_id,
        lease_generation=lease_generation,
    )
    async with session_factory() as session:
        batch = await session.scalar(
            select(AiPageMutationBatch).where(*fence.batch_conditions(utc_now()))
        )
        if batch is None:
            return
        run = await session.get(AiAgentRun, batch.run_id)
        if run is not None and run.status not in {"completed", "cancelled", "failed"}:
            # continuation 已把 run 切为 running 后再抛错时也必须收敛终态，
            # 否则过期 Batch 会失去 waiting_external 领取条件并永久卡住。
            await _fail_waiting_run(session, run=run, batch=batch, fence=fence, code=code, message=message)
            return
        await _mark_batch_failed_in_session(session, batch, fence=fence, code=code, message=message)


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
