"""文件功能：在 AI 页面写工具入口创建幂等持久化批次与任务。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_page_mutation import AiPageMutationBatch, AiPageMutationJob
from app.schemas.agent import AgentRunEvent

_ACTIVE_JOB_STATUSES = ("pending", "running")


@dataclass(frozen=True, slots=True)
class EnqueuedPageMutation:
    """返回给 CallDeferred metadata 的稳定任务引用。"""

    batch_id: str
    job_id: str
    run_step: int

    def as_metadata(self) -> dict[str, object]:
        """转换为 Pydantic AI deferred metadata。"""

        return {
            "kind": "page_mutation",
            "batch_id": self.batch_id,
            "job_id": self.job_id,
            "run_step": self.run_step,
        }


async def enqueue_page_mutation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    session_id: str,
    run_step: int,
    tool_call_id: str,
    operation: str,
    workspace_id: int,
    project_id: int | None,
    page_id: int | None = None,
    base_version_no: int | None = None,
) -> EnqueuedPageMutation:
    """创建或复用同一 tool call 的任务；页面源码仅保留在工具调用表。"""

    # Pydantic AI 每次 continuation 都会从零重新计数 run_step，不能把它作为
    # 跨 Agent.iter 的业务唯一键；持久化 Batch 自己维护同一 run 内的递增序号。
    _ = run_step
    normalized_run_id = str(run_id or "").strip()
    normalized_session_id = str(session_id or "").strip()
    normalized_tool_call_id = str(tool_call_id or "").strip()
    if not normalized_run_id or not normalized_session_id or not normalized_tool_call_id:
        raise AppException(
            status_code=409,
            code="AI_PAGE_MUTATION_CONTEXT_REQUIRED",
            detail="持久化页面变更缺少 run、session 或 tool call 标识。",
        )
    settings = get_settings()
    max_active = max(1, int(getattr(settings, "ai_page_mutation_max_active_jobs", 16)))
    max_batch_size = max(1, int(getattr(settings, "ai_page_mutation_max_batch_size", 16)))
    job_id = _stable_identifier("job", normalized_run_id, normalized_tool_call_id)

    async with session_factory() as session:
        existing = await session.scalar(
            select(AiPageMutationJob).where(
                AiPageMutationJob.run_id == normalized_run_id,
                AiPageMutationJob.tool_call_id == normalized_tool_call_id,
            )
        )
        if existing is not None:
            existing_batch = await session.get(AiPageMutationBatch, existing.batch_id)
            return EnqueuedPageMutation(
                batch_id=existing.batch_id,
                job_id=existing.job_id,
                run_step=existing_batch.run_step if existing_batch is not None else run_step,
            )
        run = await session.get(AiAgentRun, normalized_run_id)
        if run is None or run.session_id != normalized_session_id:
            raise AppException(status_code=409, code="AI_RUN_NOT_ACTIVE", detail="页面变更对应的智能体运行不存在。")
        if run.status not in {"running", "waiting_external"} or run.cancel_requested_at is not None:
            raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="智能体运行已停止，不能继续创建页面变更任务。")
        active_count = int(
            await session.scalar(
                select(func.count(AiPageMutationJob.id)).where(AiPageMutationJob.status.in_(_ACTIVE_JOB_STATUSES))
            )
            or 0
        )
        if active_count >= max_active:
            raise AppException(
                status_code=429,
                code="AI_PAGE_MUTATION_QUEUE_FULL",
                detail="AI 页面变更队列已满，请等待已有任务完成后重试。",
            )
        # 同一次工具执行尚未暂停前的多个 sequential call 共用 pending Batch；
        # 已 resuming/completed 的旧 Batch 绝不能接收下一轮工具调用。
        batch = await session.scalar(
            select(AiPageMutationBatch)
            .where(
                AiPageMutationBatch.run_id == normalized_run_id,
                AiPageMutationBatch.status == "pending",
            )
            .order_by(AiPageMutationBatch.run_step.desc())
            .limit(1)
        )
        if batch is None:
            persistent_run_step = int(
                await session.scalar(
                    select(func.max(AiPageMutationBatch.run_step)).where(
                        AiPageMutationBatch.run_id == normalized_run_id,
                    )
                )
                or 0
            ) + 1
            batch_id = _stable_identifier("batch", normalized_run_id, str(persistent_run_step))
            batch = AiPageMutationBatch(
                batch_id=batch_id,
                run_id=normalized_run_id,
                session_id=normalized_session_id,
                run_step=persistent_run_step,
                status="pending",
            )
            session.add(batch)
            await session.flush()
        else:
            batch_id = batch.batch_id
        batch_size = int(
            await session.scalar(
                select(func.count(AiPageMutationJob.id)).where(AiPageMutationJob.batch_id == batch_id)
            )
            or 0
        )
        if batch_size >= max_batch_size:
            raise AppException(
                status_code=422,
                code="AI_PAGE_MUTATION_BATCH_TOO_LARGE",
                detail=f"同一轮最多提交 {max_batch_size} 个页面变更。",
            )
        session.add(
            AiPageMutationJob(
                job_id=job_id,
                batch_id=batch_id,
                run_id=normalized_run_id,
                session_id=normalized_session_id,
                tool_call_id=normalized_tool_call_id,
                operation=operation,
                workspace_id=workspace_id,
                project_id=project_id,
                page_id=page_id,
                base_version_no=base_version_no,
                status="pending",
                attempt_count=0,
            )
        )
        try:
            await session.flush()
            # 延迟导入避免工具规格装配阶段与平台运行态形成循环依赖。
            from app.ai.platform_runtime import PlatformAgentRuntimeStore

            await PlatformAgentRuntimeStore(session, user_id=run.user_id).append_event(
                run,
                AgentRunEvent(
                    event="tool.progress",
                    run_id=run.run_id,
                    session_id=run.session_id,
                    data={
                        "tool_call_id": normalized_tool_call_id,
                        "tool_name": _operation_tool_name(operation),
                        "job_id": job_id,
                        "phase": "queued",
                        "message": "页面变更正在排队。",
                    },
                ),
                commit=False,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(AiPageMutationJob).where(
                    AiPageMutationJob.run_id == normalized_run_id,
                    AiPageMutationJob.tool_call_id == normalized_tool_call_id,
                )
            )
            if existing is None:
                raise
            batch_id = existing.batch_id
            job_id = existing.job_id
            batch = await session.get(AiPageMutationBatch, batch_id)
            if batch is None:
                raise RuntimeError("AI 页面变更任务缺少所属 Batch。")
    return EnqueuedPageMutation(batch_id=batch_id, job_id=job_id, run_step=batch.run_step)


def _stable_identifier(prefix: str, *parts: str) -> str:
    """生成长度稳定的可读业务标识，避免 run/tool call 过长触碰数据库限制。"""

    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"ai-page-{prefix}-{digest}"


def _operation_tool_name(operation: str) -> str:
    """将内部任务操作映射为 Editor 时间线使用的原始工具名。"""

    return {
        "create_page": "create_project_page",
        "apply_page_edits": "apply_page_edits",
    }.get(operation, operation)
