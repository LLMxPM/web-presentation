"""文件功能：提供页面工具共享的上下文校验与页面读取能力。"""

from __future__ import annotations

from typing import Any

from agno.run import RunContext
from agno.agent import _run as agno_agent_run
from agno.team import _run as agno_team_run
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import verify_agent_tool_token
from app.core.exceptions import AppException
from app.models.page import Page
from app.repositories.page_repository import PageRepository


async def resolve_tool_context(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: RunContext,
    *,
    required_scopes: tuple[str, ...],
    required_dependency_fields: tuple[str, ...] = ("page_id",),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """基于工具令牌校验运行上下文，并返回标准化依赖和授权 claims。"""

    dependencies = run_context.dependencies if isinstance(run_context.dependencies, dict) else {}
    run_id = str(dependencies.get("run_id") or getattr(run_context, "run_id", "") or "").strip()
    user_id = _coerce_int(dependencies.get("user_id") or dependencies.get("user_id"), "user_id")
    session_id = str(dependencies.get("session_id") or getattr(run_context, "session_id", "") or "").strip()
    agent_id = str(dependencies.get("agent_id") or "").strip()
    source = str(dependencies.get("source") or "").strip()
    token = str(dependencies.get("tool_auth_token") or "").strip()
    if not run_id or user_id is None or not session_id or not agent_id or not source or not token:
        raise AppException(status_code=401, code="AI_TOOL_CONTEXT_REQUIRED", detail="当前工具缺少必要运行上下文。")

    claims = verify_agent_tool_token(token)
    _ensure_claim_matches(claims, "run_id", run_id)
    _ensure_claim_matches(claims, "session_id", session_id)
    _ensure_claim_matches(claims, "agent_id", agent_id)
    _ensure_claim_matches(claims, "source", source)
    _ensure_claim_matches(claims, "sub", f"user:{user_id}")
    backend_session_id = _coerce_optional_str(dependencies.get("backend_session_id"))
    if backend_session_id is not None:
        _ensure_claim_matches(claims, "backend_session_id", backend_session_id)
    claim_scopes = set(claims.get("scopes") or [])
    if not set(required_scopes).issubset(claim_scopes):
        raise AppException(status_code=403, code="AI_TOOL_SCOPE_DENIED", detail="当前工具缺少所需权限。")
    await _raise_if_cancelled(run_id)
    authorized_context = {
        "user_id": user_id,
        "session_id": session_id,
        "agent_id": agent_id,
        "run_id": run_id,
        "workspace_id": _coerce_int(claims.get("workspace_id"), "workspace_id"),
        "project_id": _coerce_int(claims.get("project_id"), "project_id") if claims.get("project_id") is not None else None,
        "page_id": _coerce_int(claims.get("page_id"), "page_id") if claims.get("page_id") is not None else None,
        "component_id": _coerce_int(claims.get("component_id"), "component_id") if claims.get("component_id") is not None else None,
        "source": source,
    }
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


def _ensure_claim_matches(claims: dict[str, Any], field_name: str, expected: str) -> None:
    """校验工具令牌 claims 与 Agno dependencies 一致。"""

    if str(claims.get(field_name) or "") != expected:
        raise AppException(status_code=403, code="AI_TOOL_CONTEXT_MISMATCH", detail="工具调用上下文与授权令牌不一致。")


async def _raise_if_cancelled(run_id: str) -> None:
    """工具副作用执行前检查 Agno 取消意图。"""

    try:
        await agno_agent_run.araise_if_cancelled(run_id)
        await agno_team_run.araise_if_cancelled(run_id)
    except Exception as exc:  # noqa: BLE001
        raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="当前智能体运行已被取消。") from exc


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
