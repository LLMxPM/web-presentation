"""文件功能：提供页面工具共享的上下文校验与页面读取能力。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import verify_agent_tool_token
from app.ai.platform_tools import AgentToolContext
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun
from app.models.page import Page
from app.repositories.page_repository import PageRepository


async def resolve_tool_context(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
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

    backend_session_id = _coerce_optional_str(dependencies.get("backend_session_id"))
    claims = _resolve_authorized_claims(
        dependencies=dependencies,
        token=token,
        required_scopes=required_scopes,
        run_id=run_id,
        session_id=session_id,
        agent_id=agent_id,
        source=source,
        user_id=user_id,
        backend_session_id=backend_session_id,
    )
    await _raise_if_cancelled(session_factory, run_id)
    authorized_context = {
        "user_id": user_id,
        "session_id": session_id,
        "agent_id": _coerce_optional_str(claims.get("agent_id")) or agent_id,
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


def _resolve_authorized_claims(
    *,
    dependencies: dict[str, Any],
    token: str,
    required_scopes: tuple[str, ...],
    run_id: str,
    session_id: str,
    agent_id: str,
    source: str,
    user_id: int,
    backend_session_id: str | None,
) -> dict[str, Any]:
    """按主 token 优先、成员 token 兜底的顺序解析可授权 claims。"""

    claims = _verify_tool_claims(
        token,
        expected_agent_id=agent_id,
        run_id=run_id,
        session_id=session_id,
        source=source,
        user_id=user_id,
        backend_session_id=backend_session_id,
    )
    if _claims_include_scopes(claims, required_scopes):
        return claims

    member_tokens = dependencies.get("member_tool_auth_tokens")
    if isinstance(member_tokens, dict):
        for raw_member_agent_id, raw_member_token in member_tokens.items():
            member_agent_id = str(raw_member_agent_id or "").strip()
            member_token = str(raw_member_token or "").strip()
            if not member_agent_id or not member_token:
                continue
            member_claims = _verify_tool_claims(
                member_token,
                expected_agent_id=member_agent_id,
                run_id=run_id,
                session_id=session_id,
                source=source,
                user_id=user_id,
                backend_session_id=backend_session_id,
            )
            if _claims_include_scopes(member_claims, required_scopes):
                return member_claims

    raise AppException(status_code=403, code="AI_TOOL_SCOPE_DENIED", detail="当前工具缺少所需权限。")


def _verify_tool_claims(
    token: str,
    *,
    expected_agent_id: str,
    run_id: str,
    session_id: str,
    source: str,
    user_id: int,
    backend_session_id: str | None,
) -> dict[str, Any]:
    """校验工具 token 与本轮运行上下文的一致性。"""

    claims = verify_agent_tool_token(token)
    _ensure_claim_matches(claims, "run_id", run_id)
    _ensure_claim_matches(claims, "session_id", session_id)
    _ensure_claim_matches(claims, "agent_id", expected_agent_id)
    _ensure_claim_matches(claims, "source", source)
    _ensure_claim_matches(claims, "sub", f"user:{user_id}")
    if backend_session_id is not None:
        _ensure_claim_matches(claims, "backend_session_id", backend_session_id)
    return claims


def _claims_include_scopes(claims: dict[str, Any], required_scopes: tuple[str, ...]) -> bool:
    """判断 token claims 是否覆盖工具要求的全部 scope。"""

    return set(required_scopes).issubset(set(claims.get("scopes") or []))


def _ensure_claim_matches(claims: dict[str, Any], field_name: str, expected: str) -> None:
    """校验工具令牌 claims 与平台工具上下文一致。"""

    if str(claims.get(field_name) or "") != expected:
        raise AppException(status_code=403, code="AI_TOOL_CONTEXT_MISMATCH", detail="工具调用上下文与授权令牌不一致。")


async def _raise_if_cancelled(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> None:
    """工具副作用执行前检查平台取消标记。"""

    async with session_factory() as session:
        run_model = await session.scalar(select(AiAgentRun).where(AiAgentRun.run_id == run_id))
        if run_model is not None and run_model.cancel_requested_at is not None:
            raise AppException(status_code=409, code="AI_RUN_CANCELLED", detail="当前智能体运行已被取消。")


def _coerce_int(value: Any, field_name: str) -> int | None:
    """把平台工具 dependencies 中的整数字段规整为 int。"""

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
