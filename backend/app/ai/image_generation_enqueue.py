"""文件功能：创建幂等图片生成任务，并记录安全的模型配置快照与排队事件。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppException
from app.ai.external_task_control import enqueue_external_task
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_external_task import AiAgentExternalTask
from app.schemas.agent import AgentRunEvent
from app.services.ai_image_config_service import AiImageConfigService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.image_generation_adapters import validate_image_generation_request


@dataclass(frozen=True, slots=True)
class EnqueuedImageGeneration:
    """返回给 Pydantic AI deferred metadata 的稳定任务引用。"""

    job_id: str
    external_batch_id: str | None = None
    external_task_id: str | None = None

    def as_metadata(self) -> dict[str, object]:
        """转换成通用 external-job metadata。"""

        return {
            "kind": "image_generation",
            "job_id": self.job_id,
            **({"external_batch_id": self.external_batch_id} if self.external_batch_id else {}),
            **({"external_task_id": self.external_task_id} if self.external_task_id else {}),
        }


async def enqueue_image_generation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    session_id: str,
    tool_call_id: str,
    deferred_tool_call_id: str | None = None,
    user_id: int,
    workspace_id: int,
    project_id: int | None,
    request_payload: dict[str, Any],
    model_config_id: int | None = None,
) -> EnqueuedImageGeneration:
    """校验视觉配置与附件边界，并创建或复用同一工具调用的任务。"""

    if not run_id or not session_id or not tool_call_id:
        raise AppException(status_code=409, code="AI_IMAGE_GENERATION_CONTEXT_REQUIRED", detail="图片生成缺少 run、session 或 tool call 标识。")
    deferred_tool_call_id = str(deferred_tool_call_id or tool_call_id)
    idempotency_source = "\x1f".join((run_id, tool_call_id))
    job_id = f"ai-image-job-{hashlib.sha256(idempotency_source.encode()).hexdigest()[:32]}"
    async with session_factory() as session:
        existing = await session.scalar(
            select(AiImageGenerationJob).where(
                AiImageGenerationJob.run_id == run_id,
                AiImageGenerationJob.tool_call_id == tool_call_id,
            )
        )
        if existing is not None:
            existing_external = await session.scalar(
                select(AiAgentExternalTask).where(
                    AiAgentExternalTask.run_id == run_id,
                    AiAgentExternalTask.tool_call_id == tool_call_id,
                )
            )
            return EnqueuedImageGeneration(
                job_id=existing.job_id,
                external_batch_id=existing_external.batch_id if existing_external else None,
                external_task_id=existing_external.task_id if existing_external else None,
            )
        run = await session.get(AiAgentRun, run_id)
        if run is None or run.user_id != user_id or run.session_id != session_id:
            raise AppException(status_code=409, code="AI_RUN_NOT_ACTIVE", detail="图片生成对应的智能体运行不存在。")
        if run.status not in {"running", "waiting_external"} or run.cancel_requested_at is not None:
            raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="智能体运行已停止，不能创建图片任务。")
        external_task = await enqueue_external_task(
            session,
            run=run,
            kind="image_generation",
            tool_call_id=tool_call_id,
            deferred_tool_call_id=deferred_tool_call_id,
        )

        reference_ids = [int(item) for item in request_payload.get("reference_attachment_ids") or []]
        mask_id = request_payload.get("mask_attachment_id")
        all_ids = [*reference_ids, *([int(mask_id)] if mask_id is not None else [])]
        if all_ids:
            await AgentImageAttachmentService(session, user_id=user_id).validate_attachments_for_run(
                workspace_id=workspace_id,
                session_id=session_id,
                attachment_ids=all_ids,
            )
        image_service = AiImageConfigService(session, user_id=user_id, user_role="workspace_user")
        if model_config_id is None:
            model_config = await image_service.get_bound_model_or_raise()
        else:
            model_config = await image_service._model(model_config_id, selectable=True)
        validate_image_generation_request(model_config, request_payload)
        provider = model_config.provider_config
        job = AiImageGenerationJob(
            job_id=job_id,
            run_id=run_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            deferred_tool_call_id=deferred_tool_call_id,
            user_id=user_id,
            workspace_id=workspace_id,
            project_id=project_id,
            model_config_id=model_config.id,
            operation=str(request_payload["operation"]),
            request_json=request_payload,
            model_snapshot_json={
                "config_id": model_config.id,
                "config_name": model_config.name,
                "provider_key": provider.provider_key,
                "model_id": model_config.model_id,
            },
            status="pending",
            progress_json={"phase": "queued", "message": "图片任务正在排队。"},
            attempt_count=0,
        )
        session.add(job)
        try:
            await session.flush()
            # 延迟导入避免工具规格装配阶段与平台运行态形成循环依赖。
            from app.ai.platform_runtime import PlatformAgentRuntimeStore

            await PlatformAgentRuntimeStore(session, user_id=user_id).append_event(
                run,
                AgentRunEvent(
                    event="tool.progress",
                    run_id=run_id,
                    session_id=session_id,
                    data={
                        "tool_call_id": tool_call_id,
                        "tool_name": "generate_image",
                        "job_id": job_id,
                        "phase": "queued",
                        "message": "图片任务正在排队。",
                    },
                ),
                commit=False,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(AiImageGenerationJob).where(
                    AiImageGenerationJob.run_id == run_id,
                    AiImageGenerationJob.tool_call_id == tool_call_id,
                )
            )
            if existing is None:
                raise
            job_id = existing.job_id
            external_task = await session.scalar(
                select(AiAgentExternalTask).where(
                    AiAgentExternalTask.run_id == run_id,
                    AiAgentExternalTask.tool_call_id == tool_call_id,
                )
            )
            if external_task is None:
                raise RuntimeError("AI 图片生成任务缺少统一外部任务。")
    return EnqueuedImageGeneration(
        job_id=job_id,
        external_batch_id=external_task.batch_id,
        external_task_id=external_task.task_id,
    )
