"""文件功能：定义内容助手委派组件助手与资源助手的 Team 工具入口。"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.platform_tools import AgentToolContext, agent_tool
from app.core.exceptions import AppException

MemberAgentId = Literal["component-manager", "resource-manager"]
ResourceMemberAgentId = Literal["resource-manager"]


def build_team_delegation_tools(_session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建内容助手调用成员助手的委派工具。"""

    @agent_tool(show_result=True)
    async def delegate_task_to_member(
        run_context: AgentToolContext,
        member_id: MemberAgentId,
        task: str,
        handoff_context: str | None = None,
        expected_output: str | None = None,
    ) -> dict[str, Any]:
        """把明确的组件库或资源库任务委派给单个成员助手，并等待成员结果。"""

        executor = _resolve_delegation_executor(run_context)
        return await executor.delegate_task_to_member(
            member_id=member_id,
            task=task,
            handoff_context=handoff_context,
            expected_output=expected_output,
            delegate_tool_call_id=_current_tool_call_id(run_context),
            delegate_tool_name="delegate_task_to_member",
        )

    return [delegate_task_to_member]


def build_resource_delegation_tools(_session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建组件助手调用资源助手的委派工具。"""

    @agent_tool(show_result=True)
    async def delegate_task_to_member(
        run_context: AgentToolContext,
        member_id: ResourceMemberAgentId,
        task: str,
        handoff_context: str | None = None,
        expected_output: str | None = None,
    ) -> dict[str, Any]:
        """把明确的资源库维护任务委派给资源助手，并等待成员结果。"""

        executor = _resolve_delegation_executor(run_context)
        return await executor.delegate_task_to_member(
            member_id=member_id,
            task=task,
            handoff_context=handoff_context,
            expected_output=expected_output,
            delegate_tool_call_id=_current_tool_call_id(run_context),
            delegate_tool_name="delegate_task_to_member",
        )

    return [delegate_task_to_member]


def _resolve_delegation_executor(run_context: AgentToolContext) -> Any:
    """从工具上下文中读取委派执行器，缺失时返回标准业务错误。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    executor = dependencies.get("member_delegation_executor")
    if executor is None:
        raise AppException(
            status_code=500,
            code="AI_MEMBER_DELEGATION_UNAVAILABLE",
            detail="当前内容助手运行缺少成员委派执行器。",
        )
    return executor


def _current_tool_call_id(run_context: AgentToolContext) -> str | None:
    """读取 Pydantic AI 当前委派工具调用 ID，用于关联成员运行。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    value = dependencies.get("current_tool_call_id")
    text = str(value or "").strip()
    return text or None
