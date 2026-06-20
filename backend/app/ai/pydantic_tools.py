"""文件功能：把平台自有智能体工具规格装配为 Pydantic AI Tool。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any, get_type_hints

from pydantic_ai import RunContext
from pydantic_ai.messages import BinaryContent, ImageUrl
from pydantic_ai.tools import Tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, apply_tool_runtime_config
from app.ai.auth_tokens import build_agent_tool_token
from app.ai.image_refs import normalize_agent_image_ref
from app.ai.platform_tools import AgentToolContext, recoverable_tool_error_result
from app.ai.tool_specs import build_agent_tools_from_group_specs, list_agent_group_specs
from app.core.exceptions import AppException
from app.schemas.agent import AgentScopeContext
from app.services.auth_service import AuthContext

_NON_RECOVERABLE_TOOL_ERROR_CODES = {
    "AI_RUN_CANCELLED",
    "AI_TOOL_CONTEXT_REQUIRED",
    "AI_TOOL_CONTEXT_MISMATCH",
    "AI_TOOL_SCOPE_DENIED",
    "AI_TOOL_SCOPE_REQUIRED",
}
_RECOVERABLE_TOOL_ERROR_HINT = "请根据错误信息修正工具参数、改用其他对象；如果缺少必要信息，请询问用户。"


@dataclass(slots=True)
class AgentToolDeps:
    """Pydantic AI 工具运行依赖，内部保存平台工具鉴权上下文。"""

    dependencies: dict[str, Any]


def build_pydantic_tools(
    *,
    agent_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    runtime_config: EffectiveAgentRuntimeConfig | None,
    current: AuthContext,
    scope: AgentScopeContext,
    session_id: str,
    run_id: str,
    supports_image_input: bool,
    member_delegation_executor: Any | None = None,
) -> tuple[list[Tool[AgentToolDeps]], AgentToolDeps]:
    """构建 Pydantic AI 工具和共享 deps。"""

    raw_tools = build_agent_tools_from_group_specs(
        agent_id=agent_id,
        session_factory=session_factory,
        supports_image_input=supports_image_input,
    )
    raw_tools = apply_tool_runtime_config(agent_id=agent_id, tools=raw_tools, runtime_config=runtime_config)
    dependencies = _build_dependencies(
        agent_id=agent_id,
        current=current,
        scope=scope,
        session_id=session_id,
        run_id=run_id,
        member_delegation_executor=member_delegation_executor,
    )
    return [_wrap_platform_tool(tool_item) for tool_item in raw_tools], AgentToolDeps(dependencies=dependencies)


def _build_dependencies(
    *,
    agent_id: str,
    current: AuthContext,
    scope: AgentScopeContext,
    session_id: str,
    run_id: str,
    member_delegation_executor: Any | None = None,
) -> dict[str, Any]:
    """生成平台工具上下文校验需要的 dependencies 字典。"""

    scopes: list[str] = []
    for group in list_agent_group_specs(agent_id):
        for scope_key in group.token_scopes:
            if scope_key not in scopes:
                scopes.append(scope_key)
    token = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=agent_id,
        workspace_id=scope.workspace_id,
        project_id=scope.project_id,
        page_id=scope.page_id,
        component_id=scope.component_id,
        source=scope.source,
        scopes=tuple(scopes),
    )
    dependencies = {
        "user_id": current.user.id,
        "agent_id": agent_id,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": scope.workspace_id,
        "project_id": scope.project_id,
        "page_id": scope.page_id,
        "component_id": scope.component_id,
        "source": scope.source,
        "backend_session_id": current.backend_session_id,
        "member_tool_auth_tokens": {},
    }
    if member_delegation_executor is not None:
        dependencies["member_delegation_executor"] = member_delegation_executor
    dependencies["tool_auth_token"] = token
    return dependencies


def _wrap_platform_tool(tool_item: Any) -> Tool[AgentToolDeps]:
    """把单个平台工具包装成 Pydantic AI Tool。"""

    entrypoint = getattr(tool_item, "entrypoint", None)
    if entrypoint is None:
        raise RuntimeError(f"工具缺少 entrypoint：{getattr(tool_item, 'name', '<unknown>')}")

    async def wrapper(ctx: RunContext[AgentToolDeps], **kwargs: Any) -> Any:
        run_id = str(ctx.deps.dependencies.get("run_id") or ctx.run_id)
        session_id = str(ctx.deps.dependencies.get("session_id") or "")
        shim_context = AgentToolContext(
            run_id=run_id,
            session_id=session_id,
            user_id=str(ctx.deps.dependencies.get("user_id") or ""),
            dependencies={
                **ctx.deps.dependencies,
                "run_id": run_id,
                "session_id": session_id,
                "current_tool_call_id": ctx.tool_call_id,
                "current_tool_name": ctx.tool_name,
            },
        )
        try:
            result = entrypoint(shim_context, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return _safe_tool_result(result)
        except AppException as exc:
            if not _is_recoverable_tool_exception(exc):
                raise
            return recoverable_tool_error_result(
                code=exc.code,
                message=exc.detail,
                status_code=exc.status_code,
                hint=_RECOVERABLE_TOOL_ERROR_HINT,
            )

    tool_description = _pydantic_tool_description(tool_item, entrypoint)
    wrapper.__name__ = str(getattr(tool_item, "name", "") or entrypoint.__name__)
    wrapper.__doc__ = tool_description
    wrapper.__annotations__ = _wrapper_annotations(entrypoint)
    wrapper.__signature__ = _wrapper_signature(entrypoint)  # type: ignore[attr-defined]
    return Tool(
        wrapper,
        takes_ctx=True,
        name=str(getattr(tool_item, "name", "") or entrypoint.__name__),
        description=tool_description,
        requires_approval=bool(getattr(tool_item, "requires_confirmation", False)),
    )


def _pydantic_tool_description(tool_item: Any, entrypoint: Any) -> str:
    """合成模型实际可见的工具说明，避免丢失平台工具使用提示。"""

    description = str(getattr(tool_item, "description", "") or entrypoint.__doc__ or "").strip()
    instructions = str(getattr(tool_item, "instructions", "") or "").strip()
    if not instructions:
        return description
    if not description:
        return f"工具使用提示：{instructions}"
    return f"{description}\n\n工具使用提示：{instructions}"


def _wrapper_signature(entrypoint: Any) -> inspect.Signature:
    """把平台工具上下文参数替换为 Pydantic AI RunContext。"""

    original = inspect.signature(entrypoint)
    parameters = list(original.parameters.values())
    if parameters:
        parameters[0] = inspect.Parameter(
            parameters[0].name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=RunContext[AgentToolDeps],
        )
    return inspect.Signature(parameters=parameters, return_annotation=original.return_annotation)


def _wrapper_annotations(entrypoint: Any) -> dict[str, Any]:
    """生成包装函数的注解，供 Pydantic AI schema 生成使用。"""

    try:
        annotations = dict(get_type_hints(entrypoint, include_extras=True))
    except Exception:  # noqa: BLE001
        annotations = dict(getattr(entrypoint, "__annotations__", {}) or {})
    parameters = list(inspect.signature(entrypoint).parameters)
    if parameters:
        annotations[parameters[0]] = RunContext[AgentToolDeps]
    return annotations


def _safe_tool_result(value: Any) -> Any:
    """把平台工具返回值压成 Pydantic AI 可序列化的 JSON 值。"""

    if _looks_like_platform_tool_result(value):
        media_payload: dict[str, Any] = {}
        for key in ("images", "videos", "audios", "files"):
            media = getattr(value, key, None)
            if not media:
                continue
            media_payload[key] = list(media) if key == "images" and isinstance(media, list) else _safe_tool_result(media)
        content = getattr(value, "content", "")
        if not media_payload:
            return content
        return {"content": content, **media_payload}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, ImageUrl):
        ref = _image_ref_from_vendor_metadata(getattr(value, "vendor_metadata", None))
        if ref is not None:
            return ref
        return {
            "kind": "image-url",
            "url": value.url,
            "media_type": getattr(value, "media_type", None),
        }
    if isinstance(value, BinaryContent):
        ref = _image_ref_from_vendor_metadata(getattr(value, "vendor_metadata", None))
        if ref is not None:
            return ref
        return {
            "kind": "binary",
            "media_type": value.media_type,
            "identifier": getattr(value, "identifier", None),
            "size": len(value.data),
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "binary", "size": len(value)}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _safe_tool_result(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_tool_result(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _safe_tool_result(value.model_dump(mode="python", exclude_none=True))
        except TypeError:
            return _safe_tool_result(value.model_dump())
    if is_dataclass(value):
        return {
            field.name: _safe_tool_result(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "to_dict"):
        return _safe_tool_result(value.to_dict())
    if isinstance(value, SimpleNamespace) or hasattr(value, "__dict__"):
        return {
            str(key): _safe_tool_result(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_") and item is not None
        }
    return str(value)


def _looks_like_platform_tool_result(value: Any) -> bool:
    """识别平台 ToolResult 形态，避免把纯文本工具结果包装成复杂对象。"""

    return (
        value is not None
        and hasattr(value, "content")
        and all(hasattr(value, key) for key in ("images", "videos", "audios", "files"))
    )


def _image_ref_from_vendor_metadata(value: Any) -> dict[str, Any] | None:
    """从 Pydantic AI media vendor_metadata 中读取 Agent 图片引用。"""

    if not isinstance(value, dict):
        return None
    return normalize_agent_image_ref(value.get("agent_image_ref"))


def _is_recoverable_tool_exception(exc: AppException) -> bool:
    """区分可反馈给模型修正的业务错误和必须终止 run 的系统/权限错误。"""

    if exc.code in _NON_RECOVERABLE_TOOL_ERROR_CODES:
        return False
    if exc.status_code in {401, 403}:
        return False
    return 400 <= exc.status_code < 500
