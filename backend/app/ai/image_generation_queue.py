"""文件功能：执行图片生成持久化任务、保存资源、发出进度并自动恢复父智能体运行。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from fastapi import FastAPI
from pydantic_ai import DeferredToolResults
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.platform_tools import recoverable_tool_error_result
from app.ai.session_facade_pydantic import AgentSessionFacade
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentRun
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_llm import AiLlmConfig
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.models.user import User
from app.schemas.agent import AgentRunEvent
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.auth_service import AuthContext
from app.services.durable_job_lease_service import (
    build_durable_worker_id,
    claim_pending_jobs,
    renew_running_job_lease,
)
from app.services.image_generation.contracts import ImageProviderResult, ProviderTaskCursor, validate_advanced_options
from app.services.image_generation.registry import get_image_generation_adapter, get_image_model_spec
from app.services.image_generation_adapters import normalize_image_request

logger = logging.getLogger(__name__)
_MAX_ATTEMPTS = 3
_LEASE_SECONDS = 120
_HEARTBEAT_SECONDS = 30


async def recover_interrupted_image_generation_jobs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """把过期 running 图片任务重排；达到重试上限的任务进入 error。"""

    now = utc_now()
    async with session_factory() as session:
        jobs = list(
            (await session.scalars(
                select(AiImageGenerationJob).where(
                    AiImageGenerationJob.status == "running",
                    (AiImageGenerationJob.lease_expires_at.is_(None)) | (AiImageGenerationJob.lease_expires_at <= now),
                )
            )).all()
        )
        for job in jobs:
            job.status = "pending" if job.attempt_count < _MAX_ATTEMPTS else "error"
            job.error_code = None if job.status == "pending" else "AI_IMAGE_GENERATION_INTERRUPTED"
            job.error_message = None if job.status == "pending" else "图片任务多次中断，已停止重试。"
            job.worker_id = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            job.finished_at = utc_now() if job.status == "error" else None
        if jobs:
            await session.commit()
        return len(jobs)


async def run_ai_image_generation_queue_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
) -> None:
    """持续执行图片任务，并为已结束任务恢复对应 deferred tool call。"""

    worker_id = f"ai-image:{build_durable_worker_id()}"
    while True:
        try:
            await _cancel_one_waiting_provider_job(session_factory)
            await _promote_due_provider_jobs(session_factory)
            job_id = await _claim_one_job(session_factory, worker_id=worker_id)
            if job_id is not None:
                await _execute_job(session_factory, database_id=job_id, worker_id=worker_id)
            await _continue_one_completed_job(session_factory, app=app)
            if job_id is None:
                await recover_interrupted_image_generation_jobs_on_startup(session_factory)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("图片生成队列循环异常。", extra={"event": "ai.image_generation.queue_error"})
            await asyncio.sleep(1)


async def _claim_one_job(session_factory: async_sessionmaker[AsyncSession], *, worker_id: str) -> int | None:
    """通过条件更新原子认领一个 pending 任务，并写入可续期租约。"""

    async with session_factory() as session:
        claimed_ids = await claim_pending_jobs(
            session,
            AiImageGenerationJob,
            worker_id=worker_id,
            limit=1,
            lease_seconds=_LEASE_SECONDS,
        )
        if not claimed_ids:
            return None
        job = await session.get(AiImageGenerationJob, claimed_ids[0])
        if job is None:
            return None
        run = await session.get(AiAgentRun, job.run_id)
        if job.cancel_requested_at is not None or run is None or run.cancel_requested_at is not None or run.status in {"cancelled", "failed"}:
            job.status = "cancelled"
            job.cancel_requested_at = job.cancel_requested_at or utc_now()
            job.finished_at = utc_now()
            await session.commit()
            return None
        job.progress_json = {"phase": "running", "message": "图片正在生成。"}
        await session.commit()
        await _append_progress(session_factory, database_id=job.id, phase="running", message="图片正在生成。")
        return job.id


async def _execute_job(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
) -> None:
    """调用适配器并把每张结果同时登记为工具附件与工作空间资源。"""

    provider_cursor: ProviderTaskCursor | None = None
    heartbeat_task = asyncio.create_task(
        _renew_lease_loop(session_factory, database_id=database_id, worker_id=worker_id),
        name=f"ai-image-heartbeat-{database_id}",
    )
    try:
        async with session_factory() as session:
            job = await session.scalar(
                select(AiImageGenerationJob).where(
                    AiImageGenerationJob.id == database_id,
                    AiImageGenerationJob.status == "running",
                    AiImageGenerationJob.worker_id == worker_id,
                )
            )
            if job is None:
                return
            config = await session.scalar(
                select(AiLlmConfig)
                .where(AiLlmConfig.id == job.model_config_id)
                .options(selectinload(AiLlmConfig.provider_config))
            )
            if config is None:
                raise RuntimeError("图片生成模型配置不存在。")
            payload = dict(job.request_json or {})
            user_id = job.user_id
            workspace_id = job.workspace_id
            session_id = job.session_id
            attachment_service = AgentImageAttachmentService(session, user_id=user_id)
            references = []
            for attachment_id in payload.get("reference_attachment_ids") or []:
                attachment, content = await attachment_service.read_attachment_content(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    attachment_id=int(attachment_id),
                )
                references.append((attachment.original_name, attachment.content_type, content))
            mask = None
            if payload.get("mask_attachment_id") is not None:
                attachment, content = await attachment_service.read_attachment_content(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    attachment_id=int(payload["mask_attachment_id"]),
                )
                mask = (attachment.original_name, attachment.content_type, content)

            provider_key = str(config.provider_config.provider_key or "").strip()
            model = get_image_model_spec(provider_key, config.model_id)
            advanced_options = validate_advanced_options(model, dict(config.advanced_config_json or {}))
            provider_cursor = _provider_cursor_from_job(job)

        adapter = get_image_generation_adapter(config)
        provider_result = (
            await adapter.resume(config, model, provider_cursor)
            if provider_cursor is not None
            else await adapter.submit(
                config,
                model,
                normalize_image_request(
                    payload,
                    references=references,
                    mask=mask,
                    advanced_options=advanced_options,
                ),
            )
        )
        if provider_result.status == "waiting":
            if provider_result.cursor is None:
                raise AppException(
                    status_code=502,
                    code="AI_IMAGE_PROVIDER_RESPONSE_INVALID",
                    detail="图片供应商返回等待状态但缺少任务标识。",
                )
            await _persist_waiting_provider_result(
                session_factory,
                database_id=database_id,
                worker_id=worker_id,
                result=provider_result,
            )
            return
        generated = provider_result.images
        if not await _renew_owned_lease(session_factory, database_id=database_id, worker_id=worker_id):
            logger.warning(
                "图片生成任务租约已失效，丢弃当前供应商结果。",
                extra={"event": "ai.image_generation.lease_lost", "job_database_id": database_id},
            )
            return
        await _append_progress(session_factory, database_id=database_id, phase="saving", message="正在保存到资源库。")

        async with session_factory() as session:
            job = await session.scalar(
                select(AiImageGenerationJob).where(
                    AiImageGenerationJob.id == database_id,
                    AiImageGenerationJob.status == "running",
                    AiImageGenerationJob.worker_id == worker_id,
                )
            )
            if job is None:
                return
            run = await session.get(AiAgentRun, job.run_id)
            if job.cancel_requested_at is not None or run is None or run.cancel_requested_at is not None:
                job.status = "cancelled"
                job.finished_at = utc_now()
                job.worker_id = None
                job.lease_expires_at = None
                job.progress_json = {"phase": "error", "message": "图片任务已取消。"}
                await session.commit()
                return
            attachment_service = AgentImageAttachmentService(session, user_id=job.user_id)
            existing_attachments = list(
                (await session.scalars(
                    select(AiAgentImageAttachment).where(
                        AiAgentImageAttachment.user_id == job.user_id,
                        AiAgentImageAttachment.workspace_id == job.workspace_id,
                        AiAgentImageAttachment.session_id == job.session_id,
                        AiAgentImageAttachment.run_id == job.run_id,
                        AiAgentImageAttachment.tool_call_id == job.tool_call_id,
                        AiAgentImageAttachment.status == "active",
                    )
                )).all()
            )
            existing_by_index = {
                int((attachment.source_payload_json or {}).get("index")): attachment
                for attachment in existing_attachments
                if (attachment.source_payload_json or {}).get("job_id") == job.job_id
                and (attachment.source_payload_json or {}).get("index") is not None
            }
            output_attachments: list[dict[str, object]] = []
            output_assets: list[dict[str, object]] = []
            prefix = str(payload.get("asset_name_prefix") or "generated-image").strip()
            for index, image in enumerate(generated, start=1):
                suffix = _content_suffix(image.content_type)
                stable_name = f"{prefix}-{job.job_id[-8:]}-{index}"
                original_name = f"{stable_name}{suffix}"
                attachment = existing_by_index.get(index)
                if attachment is None:
                    attachment = await attachment_service.register_tool_image(
                        workspace_id=job.workspace_id,
                        session_id=job.session_id,
                        run_id=job.run_id,
                        content=image.content,
                        content_type=image.content_type,
                        original_name=original_name,
                        tool_name="generate_image",
                        tool_call_id=job.tool_call_id,
                        source_payload={"job_id": job.job_id, "index": index},
                        operator_id=job.user_id,
                    )
                if attachment.promoted_asset_id is None:
                    await attachment_service.promote_attachment_to_asset(
                        workspace_id=job.workspace_id,
                        session_id=job.session_id,
                        attachment_id=attachment.id,
                        name=stable_name,
                        description=payload.get("description"),
                        tags=list(payload.get("tags") or []),
                        overwrite=False,
                        operator_id=job.user_id,
                    )
                    await session.refresh(attachment)
                asset = await session.get(WorkspaceAsset, attachment.promoted_asset_id)
                output_attachments.append(
                    {
                        "id": attachment.id,
                        "original_name": attachment.original_name,
                        "content_type": attachment.content_type,
                        "file_size": attachment.file_size,
                        "promoted_asset_id": attachment.promoted_asset_id,
                    }
                )
                if asset is not None:
                    output_assets.append({"id": asset.id, "name": asset.name, "original_name": asset.original_name})
            job = await session.scalar(
                select(AiImageGenerationJob).where(
                    AiImageGenerationJob.id == database_id,
                    AiImageGenerationJob.status == "running",
                    AiImageGenerationJob.worker_id == worker_id,
                )
            )
            if job is None:
                return
            job.status = "completed"
            job.provider_status = provider_result.provider_status or "SUCCEEDED"
            job.provider_request_id = provider_result.provider_request_id or job.provider_request_id
            job.result_json = {
                "job_id": job.job_id,
                "status": "completed",
                "attachments": output_attachments,
                "assets": output_assets,
                "audit": dict(job.model_snapshot_json or {}),
            }
            job.progress_json = {"phase": "completed", "message": "图片已生成并保存到资源库。"}
            job.finished_at = utc_now()
            job.worker_id = None
            job.lease_expires_at = None
            job.heartbeat_at = None
            await session.commit()
        await _append_progress(session_factory, database_id=database_id, phase="completed", message="图片已生成并保存到资源库。")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "图片生成任务执行失败。",
            extra={"event": "ai.image_generation.failed", "job_database_id": database_id, "error_type": type(exc).__name__},
        )
        is_retryable_app_error = isinstance(exc, AppException) and bool((exc.data or {}).get("retryable"))
        if is_retryable_app_error and provider_cursor is not None:
            await _persist_waiting_provider_result(
                session_factory,
                database_id=database_id,
                worker_id=worker_id,
                result=ImageProviderResult(status="waiting", cursor=provider_cursor),
            )
            return
        await _mark_job_error(
            session_factory,
            database_id=database_id,
            worker_id=worker_id,
            code=exc.code if isinstance(exc, AppException) else "AI_IMAGE_GENERATION_FAILED",
            message=exc.detail if isinstance(exc, AppException) else "图片供应商调用或结果保存失败。",
            terminal=isinstance(exc, AppException) and not is_retryable_app_error,
        )
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task


async def _renew_lease_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
) -> None:
    """在供应商调用和资源保存期间续租，防止其他进程重复执行同一任务。"""

    while True:
        await asyncio.sleep(_HEARTBEAT_SECONDS)
        if not await _renew_owned_lease(session_factory, database_id=database_id, worker_id=worker_id):
            return


async def _renew_owned_lease(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
) -> bool:
    """仅为仍由当前 Worker 持有且未过期的任务续租。"""

    async with session_factory() as session:
        return await renew_running_job_lease(
            session,
            AiImageGenerationJob,
            job_id=database_id,
            worker_id=worker_id,
            lease_seconds=_LEASE_SECONDS,
        )


def _provider_cursor_from_job(job: AiImageGenerationJob) -> ProviderTaskCursor | None:
    """从稳定列和扩展状态重建供应商游标，供恢复、重试和取消共同使用。"""

    task_id = str(job.provider_task_id or "").strip()
    if not task_id:
        return None
    persisted = dict(job.provider_state_json or {})
    state = {
        key: value
        for key, value in persisted.items()
        if key not in {"poll_count", "next_poll_after_seconds", "cancellable"}
    }
    return ProviderTaskCursor(
        task_id=task_id,
        status=str(job.provider_status or "") or None,
        request_id=str(job.provider_request_id or "") or None,
        state=state,
        next_poll_after_seconds=float(persisted.get("next_poll_after_seconds") or 0) or None,
        cancellable=bool(persisted.get("cancellable")),
    )


async def _persist_waiting_provider_result(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
    result: ImageProviderResult,
) -> None:
    """持久化外部 task ID 并释放租约，后续轮询不得重复提交。"""

    now = utc_now()
    async with session_factory() as session:
        job = await session.scalar(
            select(AiImageGenerationJob).where(
                AiImageGenerationJob.id == database_id,
                AiImageGenerationJob.status == "running",
                AiImageGenerationJob.worker_id == worker_id,
            )
        )
        if job is None:
            return
        previous_state = dict(job.provider_state_json or {})
        poll_count = int(previous_state.get("poll_count") or 0) + (1 if job.provider_task_id else 0)
        cursor = result.cursor
        if cursor is None:
            raise AppException(status_code=502, code="AI_IMAGE_PROVIDER_RESPONSE_INVALID", detail="等待结果缺少供应商任务游标。")
        delay_seconds = cursor.next_poll_after_seconds
        if delay_seconds is None:
            delay_seconds = min(15, 2 * (2 ** min(poll_count, 3)))
        delay_seconds = min(300, max(1, float(delay_seconds)))
        job.status = "waiting_provider"
        job.provider_task_id = cursor.task_id
        job.provider_status = cursor.status or job.provider_status
        job.provider_request_id = cursor.request_id or job.provider_request_id
        job.provider_state_json = {
            **cursor.state,
            "poll_count": poll_count,
            "next_poll_after_seconds": delay_seconds,
            "cancellable": cursor.cancellable,
        }
        job.submitted_at = job.submitted_at or now
        job.next_poll_at = now + timedelta(seconds=delay_seconds)
        job.attempt_count = 0
        job.worker_id = None
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.progress_json = {"phase": "running", "message": "图片供应商正在处理任务。"}
        await session.commit()
    await _append_progress(
        session_factory,
        database_id=database_id,
        phase="running",
        message="图片供应商正在处理任务。",
    )


async def _promote_due_provider_jobs(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """把到期的外部等待任务重新放回 pending，交由统一租约流程认领。"""

    async with session_factory() as session:
        result = await session.execute(
            update(AiImageGenerationJob)
            .where(
                AiImageGenerationJob.status == "waiting_provider",
                AiImageGenerationJob.cancel_requested_at.is_(None),
                AiImageGenerationJob.next_poll_at.is_not(None),
                AiImageGenerationJob.next_poll_at <= utc_now(),
            )
            .values(status="pending", next_poll_at=None)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
        return int(result.rowcount or 0)


async def _cancel_one_waiting_provider_job(session_factory: async_sessionmaker[AsyncSession]) -> bool:
    """取消一个已提交供应商且父 run 已停止的等待任务。"""

    async with session_factory() as session:
        job = await session.scalar(
            select(AiImageGenerationJob)
            .where(
                AiImageGenerationJob.status == "waiting_provider",
                AiImageGenerationJob.cancel_requested_at.is_not(None),
            )
            .order_by(AiImageGenerationJob.id.asc())
            .limit(1)
        )
        if job is None:
            return False
        run = await session.get(AiAgentRun, job.run_id)
        should_cancel = bool(job.cancel_requested_at is not None or run is None)
        if not should_cancel:
            return False
        config = await session.scalar(
            select(AiLlmConfig)
            .where(AiLlmConfig.id == job.model_config_id)
            .options(selectinload(AiLlmConfig.provider_config))
        )
        provider_cursor = _provider_cursor_from_job(job)
        job_id = job.id
    if config is not None and provider_cursor is not None and provider_cursor.cancellable:
        with suppress(Exception):
            await get_image_generation_adapter(config).cancel(config, provider_cursor)
    async with session_factory() as session:
        job = await session.get(AiImageGenerationJob, job_id)
        if job is None or job.status != "waiting_provider":
            return False
        job.status = "cancelled"
        job.cancel_requested_at = job.cancel_requested_at or utc_now()
        job.finished_at = utc_now()
        job.next_poll_at = None
        job.progress_json = {"phase": "error", "message": "图片任务已取消。"}
        await session.commit()
    await _append_progress(session_factory, database_id=job_id, phase="error", message="图片任务已取消。")
    return True


async def _continue_one_completed_job(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    app: FastAPI,
) -> None:
    """找到一个已结束且父 run 已 waiting_external 的任务，回灌 deferred result。"""

    async with session_factory() as session:
        job = await session.scalar(
            select(AiImageGenerationJob)
            .where(
                AiImageGenerationJob.status.in_(("completed", "error", "cancelled")),
                AiImageGenerationJob.continued_at.is_(None),
            )
            .order_by(AiImageGenerationJob.finished_at.asc(), AiImageGenerationJob.id.asc())
            .limit(1)
        )
        if job is None:
            return
        run = await session.get(AiAgentRun, job.run_id)
        if run is None or run.status in {"cancelled", "failed"} or run.cancel_requested_at is not None:
            job.continued_at = utc_now()
            await session.commit()
            return
        if run.status != "waiting_external":
            return
        user = await session.get(User, job.user_id)
        if user is None or user.status != RecordStatus.ACTIVE.value:
            return
        deferred = DeferredToolResults()
        deferred.calls[job.deferred_tool_call_id] = job.result_json if job.status == "completed" else recoverable_tool_error_result(
            code=job.error_code or "AI_IMAGE_GENERATION_FAILED",
            message=job.error_message or "图片生成任务失败。",
            status_code=503,
            hint="请检查视觉模型配置、参考图片或提示词后重试。",
        )
        current = AuthContext(user=user, session_token="", backend_session_id=f"background:{run.run_id}")
        run_id = run.run_id
        job_database_id = job.id
    try:
        async with session_factory() as session:
            await AgentSessionFacade(app=app, current=current, session=session).continue_external_job_to_store(
                run_id=run_id,
                deferred_results=deferred,
                source="ai_image_generation_queue",
            )
        async with session_factory() as session:
            await session.execute(
                update(AiImageGenerationJob)
                .where(AiImageGenerationJob.id == job_database_id, AiImageGenerationJob.continued_at.is_(None))
                .values(continued_at=utc_now())
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("图片任务完成后恢复父 run 失败。", extra={"event": "ai.image_generation.continue_failed", "run_id": run_id})


async def _append_progress(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    phase: str,
    message: str,
) -> None:
    """写入可由 SSE、快照和历史统一重放的工具进度事件。"""

    with suppress(Exception):
        async with session_factory() as session:
            job = await session.get(AiImageGenerationJob, database_id)
            if job is None:
                return
            run = await session.get(AiAgentRun, job.run_id)
            if run is None:
                return
            job.progress_json = {"phase": phase, "message": message}
            member_run = await session.get(AiAgentMemberRun, job.member_run_id) if job.member_run_id else None
            await PlatformAgentRuntimeStore(session, user_id=job.user_id).append_event(
                run,
                AgentRunEvent(
                    event="member.tool.progress" if member_run is not None else "tool.progress",
                    run_id=job.run_id,
                    session_id=job.session_id,
                    data={
                        "tool_call_id": job.tool_call_id,
                        "tool_name": "generate_image",
                        "job_id": job.job_id,
                        "phase": phase,
                        "message": message,
                        **(
                            {
                                "member_run_id": member_run.member_run_id,
                                "member_agent_id": member_run.agent_id,
                                "member_agent_name": member_run.agent_name,
                            }
                            if member_run is not None
                            else {}
                        ),
                    },
                ),
                commit=False,
            )
            await session.commit()


async def _mark_job_error(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    database_id: int,
    worker_id: str,
    code: str,
    message: str,
    terminal: bool = False,
) -> None:
    """按最大重试次数重排或终止失败任务，避免保存供应商 URL 或密钥。"""

    async with session_factory() as session:
        job = await session.get(AiImageGenerationJob, database_id)
        if job is None or job.status != "running" or job.worker_id != worker_id:
            return
        terminal = terminal or job.attempt_count >= _MAX_ATTEMPTS
        job.status = "error" if terminal else "pending"
        job.error_code = code if terminal else None
        job.error_message = message if terminal else None
        job.progress_json = {
            "phase": "error" if terminal else "queued",
            "message": "图片生成失败。" if terminal else "图片生成暂时失败，正在重试。",
        }
        job.finished_at = utc_now() if terminal else None
        job.worker_id = None
        job.lease_expires_at = None
        await session.commit()
    await _append_progress(
        session_factory,
        database_id=database_id,
        phase="error" if terminal else "queued",
        message="图片生成失败。" if terminal else "图片生成暂时失败，正在重试。",
    )


def _content_suffix(content_type: str) -> str:
    """把安全图片 MIME 映射为资源文件扩展名。"""

    return {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(content_type, ".png")
