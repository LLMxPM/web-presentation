"""文件功能：把组件创建、源码编辑和重校验元数据更新加入统一外部任务队列。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.external_task_control import enqueue_external_task
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentRun
from app.models.ai_external_task import AiComponentMutationTask
from app.schemas.agent import AgentRunEvent


@dataclass(frozen=True, slots=True)
class EnqueuedComponentMutation:
    """返回给CallDeferred的统一组件任务引用。"""

    batch_id: str
    task_id: str

    def as_metadata(self) -> dict[str, str]:
        """构造通用external-job metadata。"""

        return {
            "kind": "component_mutation",
            "external_batch_id": self.batch_id,
            "external_task_id": self.task_id,
        }


async def enqueue_component_mutation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: str,
    session_id: str,
    tool_call_id: str,
    deferred_tool_call_id: str,
    member_run_id: str | None,
    operation: str,
    workspace_id: int,
    component_id: int | None = None,
    base_draft_hash: str | None = None,
    base_published_version_no: int | None = None,
    arguments: dict[str, object] | None = None,
) -> EnqueuedComponentMutation:
    """幂等创建组件统一Task及领域详情，源码仍只保存在ToolCall参数中。"""

    async with session_factory() as session:
        run = await session.get(AiAgentRun, run_id)
        if run is None or run.session_id != session_id:
            raise AppException(status_code=409, code="AI_RUN_NOT_ACTIVE", detail="组件任务对应的智能体运行不存在。")
        if run.status not in {"running", "waiting_external"} or run.cancel_requested_at is not None:
            raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="智能体运行已停止，不能创建组件任务。")
        member_run = None
        if member_run_id:
            member_run = await session.get(AiAgentMemberRun, member_run_id)
            if member_run is None or member_run.parent_run_id != run_id:
                raise AppException(status_code=409, code="AI_MEMBER_RUN_NOT_FOUND", detail="组件任务对应的成员运行不存在。")
        task = await enqueue_external_task(
            session,
            run=run,
            kind="component_mutation",
            tool_call_id=tool_call_id,
            deferred_tool_call_id=deferred_tool_call_id,
            member_run_id=member_run_id,
        )
        detail = await session.get(AiComponentMutationTask, task.task_id)
        if detail is None:
            session.add(AiComponentMutationTask(
                task_id=task.task_id,
                operation=operation,
                workspace_id=workspace_id,
                component_id=component_id,
                base_draft_hash=base_draft_hash,
                base_published_version_no=base_published_version_no,
                arguments_json=dict(arguments or {}),
            ))
        from app.ai.platform_runtime import PlatformAgentRuntimeStore

        await PlatformAgentRuntimeStore(session, user_id=run.user_id).append_event(
            run,
            AgentRunEvent(
                event="member.tool.progress" if member_run else "tool.progress",
                run_id=run.run_id,
                session_id=run.session_id,
                data={
                    "tool_call_id": tool_call_id,
                    "tool_name": operation,
                    "task_id": task.task_id,
                    "phase": "queued",
                    "message": "组件任务正在排队。",
                    **({
                        "member_run_id": member_run.member_run_id,
                        "member_agent_id": member_run.agent_id,
                        "member_agent_name": member_run.agent_name,
                    } if member_run else {}),
                },
                commit=False,
            )
        )
        await session.commit()
        return EnqueuedComponentMutation(batch_id=task.batch_id, task_id=task.task_id)
