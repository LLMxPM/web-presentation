"""文件功能：定义内容助手委派组件助手与资源助手的 Team 工具入口。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.platform_tools import AgentToolContext, agent_tool
from app.core.exceptions import AppException

MemberAgentId = Literal["component-manager", "resource-manager"]


class DelegateMemberTask(BaseModel):
    """描述批量委派中的单个成员任务。"""

    model_config = ConfigDict(extra="forbid")

    member_id: MemberAgentId = Field(..., description="目标成员助手 ID，只能是 component-manager 或 resource-manager。")
    task: str = Field(..., min_length=1, description="交给成员助手执行的具体任务。")
    handoff_context: str | None = Field(default=None, description="内容助手已掌握、成员执行任务需要继承的上下文。")
    expected_output: str | None = Field(default=None, description="期望成员返回给内容助手整合的结果格式或重点。")


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

    @agent_tool(show_result=True)
    async def delegate_task_to_members(
        run_context: AgentToolContext,
        tasks: list[DelegateMemberTask],
    ) -> dict[str, Any]:
        """按顺序把多个明确任务委派给组件助手或资源助手，并汇总成员结果。"""

        executor = _resolve_delegation_executor(run_context)
        return await executor.delegate_task_to_members(
            tasks=tasks,
            delegate_tool_call_id=_current_tool_call_id(run_context),
            delegate_tool_name="delegate_task_to_members",
        )

    return [delegate_task_to_member, delegate_task_to_members]


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
