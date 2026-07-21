"""文件功能：创建幂等图片生成任务，并记录安全的模型配置快照与排队事件。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentRun
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.enums import AiLlmSlot
from app.schemas.agent import AgentRunEvent
from app.services.ai_llm_service import AiLlmService
from app.services.agent_image_attachment_service import AgentImageAttachmentService
from app.services.image_generation_adapters import validate_image_generation_request


@dataclass(frozen=True, slots=True)
class EnqueuedImageGeneration:
    """返回给 Pydantic AI deferred metadata 的稳定任务引用。"""

    job_id: str

    def as_metadata(self) -> dict[str, object]:
        """转换成通用 external-job metadata。"""

        return {"kind": "image_generation", "job_id": self.job_id}


async def enqueue_image_generation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    session_id: str,
    tool_call_id: str,
    deferred_tool_call_id: str | None = None,
    member_run_id: str | None = None,
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
            return EnqueuedImageGeneration(job_id=existing.job_id)
        run = await session.get(AiAgentRun, run_id)
        if run is None or run.user_id != user_id or run.session_id != session_id:
            raise AppException(status_code=409, code="AI_RUN_NOT_ACTIVE", detail="图片生成对应的智能体运行不存在。")
        if run.status not in {"running", "waiting_external"} or run.cancel_requested_at is not None:
            raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="智能体运行已停止，不能创建图片任务。")
        member_run = None
        if member_run_id:
            member_run = await session.get(AiAgentMemberRun, member_run_id)
            if member_run is None or member_run.parent_run_id != run_id or member_run.session_id != session_id:
                raise AppException(status_code=409, code="AI_MEMBER_RUN_NOT_FOUND", detail="图片生成对应的资源助手运行不存在。")

        reference_ids = [int(item) for item in request_payload.get("reference_attachment_ids") or []]
        mask_id = request_payload.get("mask_attachment_id")
        all_ids = [*reference_ids, *([int(mask_id)] if mask_id is not None else [])]
        if all_ids:
            await AgentImageAttachmentService(session, user_id=user_id).validate_attachments_for_run(
                workspace_id=workspace_id,
                session_id=session_id,
                attachment_ids=all_ids,
            )
        llm_service = AiLlmService(session, user_id=user_id)
        if model_config_id is None:
            model_config = await llm_service.get_bound_config_or_raise(AiLlmSlot.IMAGE_GENERATION.value)
        else:
            model_config = await llm_service.get_selectable_active_config_or_raise(model_config_id)
            llm_service._validate_slot_model_type(AiLlmSlot.IMAGE_GENERATION.value, model_config)
        validate_image_generation_request(model_config, request_payload)
        provider = model_config.provider_config
        job = AiImageGenerationJob(
            job_id=job_id,
            run_id=run_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            deferred_tool_call_id=deferred_tool_call_id,
            member_run_id=member_run_id,
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
                    event="member.tool.progress" if member_run is not None else "tool.progress",
                    run_id=run_id,
                    session_id=session_id,
                    data={
                        "tool_call_id": tool_call_id,
                        "tool_name": "generate_image",
                        "job_id": job_id,
                        "phase": "queued",
                        "message": "图片任务正在排队。",
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
    return EnqueuedImageGeneration(job_id=job_id)
