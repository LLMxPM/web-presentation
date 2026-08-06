"""文件功能：定义统一内容助手把独立子任务委派给自身子运行的工具入口。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.platform_tools import AgentToolContext, agent_tool
from app.core.exceptions import AppException

UNIFIED_AGENT_ID = "agent-coordinator"


def build_self_delegation_tools(_session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建内容助手调用同一助手子运行的委派工具。"""

    @agent_tool(show_result=True)
    async def delegate_task_to_self(
        run_context: AgentToolContext,
        task: str,
        handoff_context: str | None = None,
        expected_output: str | None = None,
    ) -> dict[str, Any]:
        """把可独立执行的工作空间内容子任务委派给自身子运行，并等待结果。"""

        executor = _resolve_delegation_executor(run_context)
        return await executor.delegate_task_to_self(
            member_id=UNIFIED_AGENT_ID,
            task=task,
            handoff_context=handoff_context,
            expected_output=expected_output,
            delegate_tool_call_id=_current_tool_call_id(run_context),
            delegate_tool_name="delegate_task_to_self",
        )

    return [delegate_task_to_self]


def _resolve_delegation_executor(run_context: AgentToolContext) -> Any:
    """从工具上下文中读取委派执行器，缺失时返回标准业务错误。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    executor = dependencies.get("member_delegation_executor")
    if executor is None:
        raise AppException(
            status_code=500,
            code="AI_MEMBER_DELEGATION_UNAVAILABLE",
            detail="当前内容助手运行缺少自委派执行器。",
        )
    return executor


def _current_tool_call_id(run_context: AgentToolContext) -> str | None:
    """读取 Pydantic AI 当前委派工具调用 ID，用于关联成员运行。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    value = dependencies.get("current_tool_call_id")
    text = str(value or "").strip()
    return text or None
