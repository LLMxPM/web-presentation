"""文件功能：提供页面工具共享的上下文校验与页面读取能力。"""

from __future__ import annotations

from typing import Any

from agno.run import RunContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppException
from app.models.page import Page
from app.repositories.page_repository import PageRepository
from app.services.ai_agent_run_service import AiAgentRunService


async def resolve_tool_context(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: RunContext,
    *,
    required_scopes: tuple[str, ...],
    required_dependency_fields: tuple[str, ...] = ("page_id",),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """基于 run task 校验工具运行上下文，并返回标准化依赖和授权 claims。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    run_id = str(dependencies.get("run_id") or getattr(run_context, "run_id", "") or "").strip()
    user_id = _coerce_int(dependencies.get("user_id") or dependencies.get("user_id"), "user_id")
    session_id = str(dependencies.get("session_id") or getattr(run_context, "session_id", "") or "").strip()
    agent_id = str(dependencies.get("agent_id") or "").strip()
    source = str(dependencies.get("source") or "").strip()
    if not run_id or user_id is None or not session_id or not agent_id or not source:
        raise AppException(status_code=401, code="AI_TOOL_CONTEXT_REQUIRED", detail="当前工具缺少必要运行上下文。")

    async with session_factory() as session:
        authorized_context, claims = await AiAgentRunService(session).authorize_tool_call(
            run_id=run_id,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            backend_session_id=_coerce_optional_str(dependencies.get("backend_session_id")),
            source=source,
            required_scopes=required_scopes,
        )
    resolved_dependencies = {
        **dependencies,
        **authorized_context,
    }
    for field_name in required_dependency_fields:
        if resolved_dependencies.get(field_name) is None:
            raise AppException(
                status_code=401,
                code="AI_TOOL_SCOPE_REQUIRED",
                detail=f"当前工具缺少必要上下文字段：{field_name}。",
            )
    return resolved_dependencies, claims


def _coerce_int(value: Any, field_name: str) -> int | None:
    """把 Agno dependencies 中的整数字段规整为 int。"""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AppException(status_code=401, code="AI_TOOL_CONTEXT_REQUIRED", detail=f"当前工具上下文字段无效：{field_name}。") from exc


def _coerce_optional_str(value: Any) -> str | None:
    """把可选上下文字段规整为字符串。"""

    if value is None:
        return None
    return str(value)


async def get_page_or_raise(session: AsyncSession, page_id: int) -> Page:
    """按主键读取页面模型；若页面不存在则抛出统一错误。"""

    page_model = await PageRepository(session).get_by_id(page_id)
    if page_model is None:
        raise AppException(status_code=404, code="PAGE_NOT_FOUND", detail="页面不存在。")
    return page_model
