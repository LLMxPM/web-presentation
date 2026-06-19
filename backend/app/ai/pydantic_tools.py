"""文件功能：把现有智能体工具规格和 Agno Function 桥接为 Pydantic AI Tool。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, get_type_hints

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, apply_tool_runtime_config
from app.ai.auth_tokens import build_agent_tool_token
from app.ai.tool_specs import build_agent_tools_from_group_specs, list_agent_group_specs
from app.schemas.agent import AgentScopeContext
from app.services.auth_service import AuthContext


@dataclass(slots=True)
class AgentToolDeps:
    """Pydantic AI 工具运行依赖，内部再转换为旧工具需要的 dependencies。"""

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
    )
    return [_wrap_agno_function(tool_item) for tool_item in raw_tools], AgentToolDeps(dependencies=dependencies)


def _build_dependencies(
    *,
    agent_id: str,
    current: AuthContext,
    scope: AgentScopeContext,
    session_id: str,
    run_id: str,
) -> dict[str, Any]:
    """生成旧工具上下文校验需要的 dependencies 字典。"""

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
    dependencies["tool_auth_token"] = token
    return dependencies


def _wrap_agno_function(tool_item: Any) -> Tool[AgentToolDeps]:
    """把单个 Agno Function 包装成 Pydantic AI Tool。"""

    entrypoint = getattr(tool_item, "entrypoint", None)
    if entrypoint is None:
        raise RuntimeError(f"工具缺少 entrypoint：{getattr(tool_item, 'name', '<unknown>')}")

    async def wrapper(ctx: RunContext[AgentToolDeps], **kwargs: Any) -> Any:
        shim_context = SimpleNamespace(
            dependencies={
                **ctx.deps.dependencies,
                "run_id": ctx.deps.dependencies.get("run_id") or ctx.run_id,
            },
            run_id=ctx.deps.dependencies.get("run_id") or ctx.run_id,
            session_id=ctx.deps.dependencies.get("session_id"),
        )
        result = entrypoint(shim_context, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    wrapper.__name__ = str(getattr(tool_item, "name", "") or entrypoint.__name__)
    wrapper.__doc__ = str(getattr(tool_item, "description", "") or entrypoint.__doc__ or "")
    wrapper.__annotations__ = _wrapper_annotations(entrypoint)
    wrapper.__signature__ = _wrapper_signature(entrypoint)  # type: ignore[attr-defined]
    return Tool(
        wrapper,
        takes_ctx=True,
        name=str(getattr(tool_item, "name", "") or entrypoint.__name__),
        description=str(getattr(tool_item, "description", "") or ""),
        requires_approval=bool(getattr(tool_item, "requires_confirmation", False)),
    )


def _wrapper_signature(entrypoint: Any) -> inspect.Signature:
    """把旧 run_context 参数替换为 Pydantic AI RunContext。"""

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
