"""文件功能：统一同步页面、图片、组件任务状态并以租约保护一次性恢复模型。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from pydantic_ai import DeferredToolResults
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.external_task_control import consume_external_batch_results
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.platform_tools import recoverable_tool_error_result
from app.ai.run_write_fence import AgentRunWriteFenceLost, ExternalBatchContinuationWriteFence
from app.ai.session_facade_pydantic import AgentSessionFacade
from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_page_mutation import AiPageMutationBatch, AiPageMutationJob
from app.models.enums import RecordStatus
from app.models.user import User
from app.schemas.agent import AgentRunEvent
from app.services.auth_service import AuthContext

logger = logging.getLogger(__name__)
_TASK_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


class _ExternalContinuationLeaseLost(RuntimeError):
    """表示统一Batch续跑已失去租约，当前模型调用必须主动终止。"""


async def run_ai_external_task_coordinator(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
) -> None:
    """持续同步领域任务、恢复过期租约并一次性回灌已就绪Batch。"""

    worker_id = f"ai-external-continuation-{uuid4().hex[:12]}"
    poll_interval = max(0.05, float(get_settings().ai_page_mutation_poll_interval_seconds))
    cleanup_counter = 0
    while True:
        try:
            await synchronize_external_task_states(session_factory)
            await recover_external_continuations(session_factory)
            await audit_external_state_consistency(session_factory)
            cleanup_counter += 1
            if cleanup_counter >= max(1, int(60 / poll_interval)):
                await cleanup_expired_external_results(session_factory)
                cleanup_counter = 0
            claimed = await _claim_ready_batch(session_factory, worker_id=worker_id)
            if claimed is None:
                await asyncio.sleep(poll_interval)
                continue
            await _continue_batch(
                session_factory,
                app=app,
                batch_id=claimed[0],
                worker_id=worker_id,
                lease_generation=claimed[1],
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("统一AI外部任务协调器异常。", extra={"event": "ai.external.coordinator.failed"})
            await asyncio.sleep(poll_interval)


async def synchronize_external_task_states(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """把迁移期间保留的页面和图片领域状态投影到统一Task，并推进就绪Batch。"""

    async with session_factory() as session:
        tasks = list(
            (
                await session.scalars(
                    select(AiAgentExternalTask).where(AiAgentExternalTask.status.not_in(_TASK_TERMINAL))
                )
            ).all()
        )
        now = utc_now()
        for task in tasks:
            domain_status: str | None = None
            result = None
            error_code = None
            error_message = None
            if task.kind == "page_mutation":
                job = await session.scalar(
                    select(AiPageMutationJob).where(
                        AiPageMutationJob.run_id == task.run_id,
                        AiPageMutationJob.tool_call_id == task.tool_call_id,
                    )
                )
                if job is not None:
                    domain_status = {
                        "pending": "pending", "running": "running", "succeeded": "succeeded",
                        "failed": "failed", "cancelled": "cancelled",
                    }.get(job.status)
                    result, error_code, error_message = job.result_json, job.error_code, job.error_message
                    if domain_status == "running":
                        task.worker_id = job.worker_id
                        task.lease_expires_at = job.lease_expires_at
                        task.heartbeat_at = job.heartbeat_at
                        task.attempt_count = job.attempt_count
            elif task.kind == "image_generation":
                job = await session.scalar(
                    select(AiImageGenerationJob).where(
                        AiImageGenerationJob.run_id == task.run_id,
                        AiImageGenerationJob.tool_call_id == task.tool_call_id,
                    )
                )
                if job is not None:
                    domain_status = {
                        "pending": "pending", "running": "running", "waiting_provider": "waiting_provider",
                        "completed": "succeeded", "error": "failed", "cancelled": "cancelled",
                    }.get(job.status)
                    result, error_code, error_message = job.result_json, job.error_code, job.error_message
                    if domain_status == "running":
                        task.worker_id = job.worker_id
                        task.lease_expires_at = job.lease_expires_at
                        task.heartbeat_at = job.heartbeat_at
                        task.attempt_count = job.attempt_count
            if domain_status is None or domain_status == task.status:
                continue
            task.status = domain_status
            task.progress_at = now
            task.result_json = result
            task.error_code = error_code
            task.error_message = error_message
            if domain_status in _TASK_TERMINAL:
                task.finished_at = now
                task.worker_id = None
                task.lease_expires_at = None
                task.heartbeat_at = None
            elif domain_status == "waiting_provider":
                task.worker_id = None
                task.lease_expires_at = None
                task.heartbeat_at = None
        batches = list(
            (await session.scalars(select(AiAgentExternalBatch).where(AiAgentExternalBatch.status == "waiting_tasks"))).all()
        )
        for batch in batches:
            nonterminal = int(
                await session.scalar(
                    select(func.count(AiAgentExternalTask.id)).where(
                        AiAgentExternalTask.batch_id == batch.batch_id,
                        AiAgentExternalTask.status.not_in(_TASK_TERMINAL),
                    )
                )
                or 0
            )
            total = int(
                await session.scalar(select(func.count(AiAgentExternalTask.id)).where(AiAgentExternalTask.batch_id == batch.batch_id))
                or 0
            )
            if total and not nonterminal:
                batch.status = "ready"
                batch.updated_at = now
        await session.commit()


async def recover_external_continuations(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """恢复过期续跑租约，并将resolving Requirement回退为可重试pending。"""

    now = utc_now()
    async with session_factory() as session:
        batches = list(
            (
                await session.scalars(
                    select(AiAgentExternalBatch).where(
                        AiAgentExternalBatch.status == "resuming",
                        (AiAgentExternalBatch.lease_expires_at.is_(None))
                        | (AiAgentExternalBatch.lease_expires_at <= now),
                    )
                )
            ).all()
        )
        for batch in batches:
            run = await session.get(AiAgentRun, batch.run_id)
            requirement = (
                await session.scalar(
                    select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == batch.requirement_id)
                )
                if batch.requirement_id
                else None
            )
            # 续跑事务已持久化模型历史、只有收尾事务丢失时，补齐消费而不能再次回灌。
            if requirement is not None and requirement.status == "resolved":
                await consume_external_batch_results(session, batch=batch)
                await _finish_legacy_domain_rows(session, batch_id=batch.batch_id)
                continue
            cancelled = run is None or run.cancel_requested_at is not None or run.status in {"cancelling", "cancelled", "failed"}
            batch.status = "cancelled" if cancelled else "ready"
            batch.worker_id = None
            batch.lease_expires_at = None
            batch.heartbeat_at = None
            batch.lease_generation += 1
            if cancelled:
                batch.finished_at = now
            if requirement is not None and requirement.status == "resolving":
                requirement.status = "cancelled" if cancelled else "pending"
                requirement.resolved_at = now if cancelled else None
        if batches:
            await session.commit()


async def audit_external_state_consistency(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """按明确关联关系巡检waiting_external，并传播父Run终态与可修复状态。"""

    settings = get_settings()
    grace_seconds = max(10.0, 2 * float(settings.ai_page_mutation_poll_interval_seconds))
    now = utc_now()
    cutoff = now - timedelta(seconds=grace_seconds)
    async with session_factory() as session:
        cancelling_runs = list(
            (await session.scalars(select(AiAgentRun).where(AiAgentRun.status == "cancelling"))).all()
        )
        for run in cancelling_runs:
            total = int(
                await session.scalar(
                    select(func.count(AiAgentExternalTask.id)).where(AiAgentExternalTask.run_id == run.run_id)
                )
                or 0
            )
            if not total:
                continue
            active_resuming = await session.scalar(
                select(AiAgentExternalBatch.batch_id).where(
                    AiAgentExternalBatch.run_id == run.run_id,
                    AiAgentExternalBatch.status == "resuming",
                    AiAgentExternalBatch.lease_expires_at.is_not(None),
                    AiAgentExternalBatch.lease_expires_at > now,
                ).limit(1)
            )
            if active_resuming is not None:
                continue
            remaining = int(
                await session.scalar(
                    select(func.count(AiAgentExternalTask.id)).where(
                        AiAgentExternalTask.run_id == run.run_id,
                        AiAgentExternalTask.status.not_in(_TASK_TERMINAL),
                    )
                )
                or 0
            )
            if remaining:
                continue
            run.status = "cancelled"
            run.pending_requirement_json = None
            run.finished_at = now
            await PlatformAgentRuntimeStore(session, user_id=run.user_id).append_event(
                run,
                AgentRunEvent(
                    event="run.cancelled",
                    run_id=run.run_id,
                    session_id=run.session_id,
                    data={"message": "后台任务已停止，运行取消完成。"},
                ),
                commit=False,
            )
        # 父Run终态后，统一控制面不得继续保留可执行任务。
        terminal_runs = list(
            (
                await session.scalars(
                    select(AiAgentRun).where(AiAgentRun.status.in_(("completed", "cancelled", "failed")))
                )
            ).all()
        )
        for run in terminal_runs:
            active_resuming = await session.scalar(
                select(AiAgentExternalBatch.batch_id).where(
                    AiAgentExternalBatch.run_id == run.run_id,
                    AiAgentExternalBatch.status == "resuming",
                    AiAgentExternalBatch.lease_expires_at.is_not(None),
                    AiAgentExternalBatch.lease_expires_at > now,
                ).limit(1)
            )
            # 成功续跑已提交Run终态、Batch收尾尚未提交时，保留有效租约给协调器完成结果消费。
            if active_resuming is not None:
                continue
            tasks = list(
                (
                    await session.scalars(
                        select(AiAgentExternalTask).where(
                            AiAgentExternalTask.run_id == run.run_id,
                            AiAgentExternalTask.status.not_in(_TASK_TERMINAL),
                        )
                    )
                ).all()
            )
            for task in tasks:
                task.cancel_requested_at = task.cancel_requested_at or now
                if task.status == "pending":
                    task.status = "cancelled"
                    task.finished_at = now
            await session.execute(
                update(AiAgentExternalBatch)
                .where(
                    AiAgentExternalBatch.run_id == run.run_id,
                    AiAgentExternalBatch.status.in_(("collecting", "waiting_tasks", "ready")),
                )
                .values(status="cancelled", finished_at=now)
            )
            await session.execute(
                update(AiAgentRequirement)
                .where(
                    AiAgentRequirement.run_id == run.run_id,
                    AiAgentRequirement.status.in_(("pending", "resolving")),
                )
                .values(status="cancelled", resolved_at=now)
            )
            from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentToolCall

            await session.execute(
                update(AiAgentMemberRun)
                .where(
                    AiAgentMemberRun.parent_run_id == run.run_id,
                    AiAgentMemberRun.status.in_(("running", "waiting_external")),
                )
                .values(status="cancelled", finished_at=now)
            )
            await session.execute(
                update(AiAgentToolCall)
                .where(
                    AiAgentToolCall.run_id == run.run_id,
                    AiAgentToolCall.status.in_(("running", "waiting_external")),
                )
                .values(status="cancelled", message="父级运行已终态。")
            )

        waiting_runs = list(
            (
                await session.scalars(
                    select(AiAgentRun).where(
                        AiAgentRun.status == "waiting_external",
                        AiAgentRun.updated_at <= cutoff,
                    )
                )
            ).all()
        )
        for run in waiting_runs:
            requirements = list(
                (
                    await session.scalars(
                        select(AiAgentRequirement).where(
                            AiAgentRequirement.run_id == run.run_id,
                            AiAgentRequirement.kind == "external_job",
                            AiAgentRequirement.status.in_(("pending", "resolving")),
                        )
                    )
                ).all()
            )
            if len(requirements) != 1:
                await _fail_waiting_run(session, run=run, message="等待外部任务的运行缺少唯一活动Requirement。")
                continue
            requirement = requirements[0]
            batch = await session.scalar(
                select(AiAgentExternalBatch).where(
                    AiAgentExternalBatch.requirement_id == requirement.requirement_id,
                    AiAgentExternalBatch.status.in_(("waiting_tasks", "ready", "resuming")),
                )
            )
            if batch is None:
                await _fail_waiting_run(session, run=run, message="外部Requirement没有绑定非终态Batch。")
                requirement.status = "failed"
                continue
            task_count = int(
                await session.scalar(
                    select(func.count(AiAgentExternalTask.id)).where(AiAgentExternalTask.batch_id == batch.batch_id)
                )
                or 0
            )
            if task_count == 0:
                batch.status = "failed"
                batch.error_code = "AI_EXTERNAL_STATE_INCONSISTENT"
                batch.error_message = "外部Batch没有Task。"
                batch.finished_at = now
                await _fail_waiting_run(session, run=run, message=batch.error_message)
                requirement.status = "failed"
                continue
            if requirement.member_run_id:
                from app.models.ai_agent_runtime import AiAgentMemberRun

                member = await session.get(AiAgentMemberRun, requirement.member_run_id)
                if member is None or member.status not in {"running", "waiting_external"}:
                    await _fail_waiting_run(session, run=run, message="成员Requirement引用不存在或已终态的成员Run。")
                    requirement.status = "failed"
        await session.commit()


async def _fail_waiting_run(session: AsyncSession, *, run: AiAgentRun, message: str) -> None:
    """把不可自动修复的外部状态孤儿收敛为父Run失败。"""

    run.status = "failed"
    run.error_code = "AI_EXTERNAL_STATE_INCONSISTENT"
    run.error_message = message
    run.pending_requirement_json = None
    run.finished_at = utc_now()


async def cleanup_expired_external_results(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int = 7,
) -> int:
    """清理终态未消费的大结果；续跑失败且仍在保留期内的结果不动。"""

    cutoff = utc_now() - timedelta(days=max(1, retention_days))
    async with session_factory() as session:
        tasks = list(
            (
                await session.scalars(
                    select(AiAgentExternalTask).where(
                        AiAgentExternalTask.status.in_(_TASK_TERMINAL),
                        AiAgentExternalTask.result_json.is_not(None),
                        AiAgentExternalTask.result_consumed_at.is_(None),
                        AiAgentExternalTask.finished_at.is_not(None),
                        AiAgentExternalTask.finished_at <= cutoff,
                    ).limit(100)
                )
            ).all()
        )
        for task in tasks:
            value = task.result_json
            summary = dict(task.result_summary_json or {})
            summary.update({"kind": task.kind, "status": task.status, "expired_without_consumption": True})
            if isinstance(value, dict):
                for key in ("page_id", "component_id", "job_id", "success", "applied"):
                    if key in value:
                        summary[key] = value[key]
            task.result_summary_json = summary
            task.result_json = None
        if tasks:
            await session.commit()
        return len(tasks)


async def _claim_ready_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    worker_id: str,
) -> tuple[str, int] | None:
    """以CAS认领一个ready Batch，并同时把Requirement置为resolving。"""

    settings = get_settings()
    now = utc_now()
    lease_seconds = max(int(settings.durable_job_lease_seconds), int(settings.durable_job_heartbeat_seconds) * 3)
    async with session_factory() as session:
        candidate = await session.scalar(
            select(AiAgentExternalBatch)
            .join(AiAgentRun, AiAgentRun.run_id == AiAgentExternalBatch.run_id)
            .where(
                AiAgentExternalBatch.status == "ready",
                AiAgentRun.status == "waiting_external",
                AiAgentRun.cancel_requested_at.is_(None),
            )
            .order_by(AiAgentExternalBatch.created_at.asc())
            .limit(1)
        )
        if candidate is None:
            return None
        generation = candidate.lease_generation + 1
        result = await session.execute(
            update(AiAgentExternalBatch)
            .where(
                AiAgentExternalBatch.batch_id == candidate.batch_id,
                AiAgentExternalBatch.status == "ready",
                AiAgentExternalBatch.lease_generation == candidate.lease_generation,
            )
            .values(
                status="resuming",
                worker_id=worker_id,
                lease_generation=generation,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                heartbeat_at=now,
                started_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) != 1:
            await session.rollback()
            return None
        if candidate.requirement_id:
            await session.execute(
                update(AiAgentRequirement)
                .where(
                    AiAgentRequirement.requirement_id == candidate.requirement_id,
                    AiAgentRequirement.status.in_(("pending", "resolving")),
                )
                .values(status="resolving")
            )
        await session.commit()
        return candidate.batch_id, generation


async def _continue_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
    batch_id: str,
    worker_id: str,
    lease_generation: int,
) -> None:
    """构造整批deferred results，在通用写围栏内恢复父级或成员模型。"""

    fence = ExternalBatchContinuationWriteFence(batch_id, worker_id, lease_generation)
    lease_lost = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_batch(session_factory, fence=fence, lease_lost=lease_lost),
        name=f"ai-external-heartbeat-{batch_id}",
    )
    continuation_task: asyncio.Task[str] | None = None
    lease_waiter: asyncio.Task[bool] | None = None
    try:
        async with session_factory() as session:
            batch = await session.scalar(select(AiAgentExternalBatch).where(*fence.batch_conditions(utc_now())))
            if batch is None:
                return
            run = await session.get(AiAgentRun, batch.run_id)
            requirement = await session.scalar(
                select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == batch.requirement_id)
            ) if batch.requirement_id else None
            tasks = list(
                (await session.scalars(select(AiAgentExternalTask).where(AiAgentExternalTask.batch_id == batch_id))).all()
            )
            if run is None or requirement is None or not tasks:
                await _fail_inconsistent(session, batch=batch, run=run)
                return
            user = await session.get(User, run.user_id)
            if user is None or user.status != RecordStatus.ACTIVE.value:
                await _fail_inconsistent(session, batch=batch, run=run, code="AUTH_DISABLED")
                return
            deferred = DeferredToolResults()
            for task in tasks:
                deferred.calls[task.deferred_tool_call_id] = (
                    task.result_json
                    if task.status == "succeeded"
                    else recoverable_tool_error_result(
                        code=task.error_code or "AI_EXTERNAL_TASK_FAILED",
                        message=task.error_message or "外部任务执行失败。",
                        status_code=503,
                        hint="请根据错误信息调整参数后重新调用。",
                    )
                )
            current = AuthContext(user=user, session_token="", backend_session_id=f"background:{run.run_id}")
            run_id = run.run_id
        async def continue_model() -> str:
            """在独立短会话中执行受围栏保护的模型续跑。"""

            async with session_factory() as session:
                return await AgentSessionFacade(app=app, current=current, session=session).continue_external_job_to_store(
                    run_id=run_id,
                    deferred_results=deferred,
                    continuation_fence=fence,
                    source="ai_external_task_queue",
                )

        continuation_task = asyncio.create_task(continue_model(), name=f"ai-external-model-{batch_id}")
        lease_waiter = asyncio.create_task(lease_lost.wait(), name=f"ai-external-lease-waiter-{batch_id}")
        completed, _ = await asyncio.wait(
            {continuation_task, lease_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lease_waiter in completed:
            if not continuation_task.done():
                continuation_task.cancel()
                with suppress(asyncio.CancelledError):
                    await continuation_task
            else:
                # 同时完成时取走Task异常，避免后台出现未检索异常；租约丢失仍优先判定。
                with suppress(asyncio.CancelledError, Exception):
                    await continuation_task
            raise _ExternalContinuationLeaseLost()
        await continuation_task
        if lease_lost.is_set():
            raise _ExternalContinuationLeaseLost()
        async with session_factory() as session:
            batch = await session.scalar(select(AiAgentExternalBatch).where(*fence.batch_conditions(utc_now())))
            if batch is None:
                raise AgentRunWriteFenceLost("统一外部Batch收尾时租约已失效。")
            await consume_external_batch_results(session, batch=batch)
            await _finish_legacy_domain_rows(session, batch_id=batch_id)
            await session.commit()
    except (AgentRunWriteFenceLost, _ExternalContinuationLeaseLost):
        logger.warning("统一外部Batch续跑失去租约。", extra={"batch_id": batch_id})
    except asyncio.CancelledError:
        if continuation_task is not None and not continuation_task.done():
            continuation_task.cancel()
            with suppress(asyncio.CancelledError):
                await continuation_task
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("统一外部Batch续跑失败。", extra={"batch_id": batch_id})
        async with session_factory() as session:
            batch = await session.get(AiAgentExternalBatch, batch_id)
            if batch is not None and batch.status == "resuming" and batch.worker_id == worker_id:
                batch.status = "failed"
                batch.error_code = "AI_EXTERNAL_CONTINUE_FAILED"
                batch.error_message = str(exc)[:2000]
                batch.finished_at = utc_now()
                if batch.requirement_id:
                    requirement = await session.scalar(
                        select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == batch.requirement_id)
                    )
                    if requirement is not None and requirement.status in {"pending", "resolving"}:
                        requirement.status = "failed"
                        requirement.resolved_payload_json = {
                            "code": batch.error_code,
                            "message": batch.error_message,
                        }
                        requirement.resolved_at = utc_now()
                run = await session.get(AiAgentRun, batch.run_id)
                if run is not None and run.status == "waiting_external":
                    run.status = "failed"
                    run.pending_requirement_json = None
                    run.error_code = batch.error_code
                    run.error_message = batch.error_message
                    run.finished_at = utc_now()
                await session.commit()
    finally:
        if lease_waiter is not None and not lease_waiter.done():
            lease_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await lease_waiter
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _heartbeat_batch(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    fence: ExternalBatchContinuationWriteFence,
    lease_lost: asyncio.Event,
) -> None:
    """续跑期间周期延长租约；失败时通知调用方取消模型请求。"""

    settings = get_settings()
    interval = max(1, int(settings.durable_job_heartbeat_seconds))
    lease_seconds = max(int(settings.durable_job_lease_seconds), interval * 3)
    while True:
        try:
            await asyncio.sleep(interval)
            now = utc_now()
            async with session_factory() as session:
                result = await session.execute(
                    update(AiAgentExternalBatch)
                    .where(*fence.batch_conditions(now))
                    .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=lease_seconds))
                )
                await session.commit()
            if int(result.rowcount or 0) != 1:
                lease_lost.set()
                return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning(
                "统一外部Batch续租失败，当前模型续跑将被取消。",
                exc_info=True,
                extra={"event": "ai.external.continuation_heartbeat_failed", "batch_id": fence.batch_id},
            )
            lease_lost.set()
            return


async def _finish_legacy_domain_rows(session: AsyncSession, *, batch_id: str) -> None:
    """统一结果消费后清理迁移期领域结果副本和旧页面Batch。"""

    tasks = list((await session.scalars(select(AiAgentExternalTask).where(AiAgentExternalTask.batch_id == batch_id))).all())
    page_tool_ids = [task.tool_call_id for task in tasks if task.kind == "page_mutation"]
    image_tool_ids = [task.tool_call_id for task in tasks if task.kind == "image_generation"]
    if page_tool_ids:
        page_jobs = list(
            (await session.scalars(select(AiPageMutationJob).where(
                AiPageMutationJob.run_id == tasks[0].run_id,
                AiPageMutationJob.tool_call_id.in_(page_tool_ids),
            ))).all()
        )
        old_batch_ids = {job.batch_id for job in page_jobs}
        for job in page_jobs:
            job.result_json = None
        if old_batch_ids:
            await session.execute(
                update(AiPageMutationBatch)
                .where(AiPageMutationBatch.batch_id.in_(old_batch_ids), AiPageMutationBatch.status == "pending")
                .values(status="completed", finished_at=utc_now())
            )
    if image_tool_ids:
        await session.execute(
            update(AiImageGenerationJob)
            .where(
                AiImageGenerationJob.run_id == tasks[0].run_id,
                AiImageGenerationJob.tool_call_id.in_(image_tool_ids),
            )
            .values(result_json=None, provider_state_json=None)
        )


async def _fail_inconsistent(
    session: AsyncSession,
    *,
    batch: AiAgentExternalBatch,
    run: AiAgentRun | None,
    code: str = "AI_EXTERNAL_STATE_INCONSISTENT",
) -> None:
    """收敛缺失Run、Requirement或Task的统一Batch。"""

    batch.status = "failed"
    batch.error_code = code
    batch.error_message = "外部任务状态不完整，无法继续模型运行。"
    batch.finished_at = utc_now()
    if run is not None:
        run.status = "failed"
        run.error_code = code
        run.error_message = batch.error_message
        run.finished_at = utc_now()
    await session.commit()
