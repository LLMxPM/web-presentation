"""文件功能：定义内容助手运行时工具装配与工具可见性说明。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, apply_tool_runtime_config, is_tool_enabled
from app.ai.tool_specs import (
    AGENT_COORDINATOR_AGENT_ID,
    build_agent_tools_from_group_specs,
    build_group_tools,
    list_disclosable_agent_group_specs,
)

UNIFIED_AGENT_ID = AGENT_COORDINATOR_AGENT_ID

ToolBuilder = Callable[[], list[Any]]


@dataclass(slots=True, frozen=True)
class ToolGroupDefinition:
    """描述内容助手内部工具集合，用于配置说明、参数 schema 与 token scope 汇总。"""

    key: str
    label: str
    description: str
    required_context_fields: tuple[str, ...]
    token_scopes: tuple[str, ...]
    tool_keys: tuple[str, ...]
    build_tools: ToolBuilder
    requires_image_input: bool = False


def build_unified_agent_tools(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    supports_image_input: bool | None = None,
) -> list[Any]:
    """构建内容助手本轮可见的全部配置工具，仅按用户配置和图片输入能力过滤。"""

    tools = build_agent_tools_from_group_specs(
        agent_id=UNIFIED_AGENT_ID,
        session_factory=session_factory,
        supports_image_input=supports_image_input,
    )
    return apply_tool_runtime_config(
        agent_id=UNIFIED_AGENT_ID,
        tools=tools,
        runtime_config=agent_config,
    )


def get_tool_group_definitions(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    supports_image_input: bool | None = None,
) -> dict[str, ToolGroupDefinition]:
    """返回内容助手工具集合定义；这些集合不再参与 scope 裁剪。"""

    definitions = {
        group.key: ToolGroupDefinition(
            key=group.key,
            label=group.label,
            description=group.description,
            required_context_fields=group.required_context_fields,
            token_scopes=group.token_scopes,
            tool_keys=group.tool_keys,
            requires_image_input=group.requires_image_input,
            build_tools=lambda group_key=group.key: build_group_tools(
                agent_id=UNIFIED_AGENT_ID,
                group_key=group_key,
                session_factory=session_factory,
            ),
        )
        for group in list_disclosable_agent_group_specs(UNIFIED_AGENT_ID)
        if supports_image_input is None or not group.requires_image_input or supports_image_input
    }
    if agent_config is None:
        return definitions
    filtered_definitions: dict[str, ToolGroupDefinition] = {}
    for key, definition in definitions.items():
        enabled_tool_keys = tuple(
            tool_key
            for tool_key in definition.tool_keys
            if is_tool_enabled(agent_id=UNIFIED_AGENT_ID, tool_key=tool_key, runtime_config=agent_config)
        )
        if enabled_tool_keys:
            filtered_definitions[key] = replace(definition, tool_keys=enabled_tool_keys)
    return filtered_definitions


def resolve_allowed_tool_group_keys(
    scope: Any,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    supports_image_input: bool | None = None,
) -> tuple[str, ...]:
    """兼容旧调用：返回当前模型能力下的全部工具集合 key，不按业务 scope 裁剪。"""

    _ = scope
    return tuple(get_tool_group_definitions(
        session_factory=session_factory,
        agent_config=agent_config,
        supports_image_input=supports_image_input,
    ))


def resolve_tool_scopes_for_groups(
    *,
    enabled_tool_groups: Iterable[str],
    session_factory: async_sessionmaker[AsyncSession],
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    supports_image_input: bool | None = None,
) -> tuple[str, ...]:
    """兼容旧调用：按传入工具集合返回 token scope；新运行时使用 resolve_unified_tool_scopes。"""

    definitions = get_tool_group_definitions(
        session_factory=session_factory,
        agent_config=agent_config,
        supports_image_input=supports_image_input,
    )
    scopes: list[str] = []
    for group_key in normalize_tool_group_keys(enabled_tool_groups):
        definition = definitions.get(group_key)
        if definition is None:
            continue
        for scope in definition.token_scopes:
            if scope not in scopes:
                scopes.append(scope)
    return tuple(scopes)


def resolve_unified_tool_scopes(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    supports_image_input: bool | None = None,
) -> tuple[str, ...]:
    """返回内容助手全量直接工具所需的 token scope，仅受图片输入能力和用户配置影响。"""

    definitions = get_tool_group_definitions(
        session_factory=session_factory,
        agent_config=agent_config,
        supports_image_input=supports_image_input,
    )
    scopes: list[str] = []
    for definition in definitions.values():
        for scope in definition.token_scopes:
            if scope not in scopes:
                scopes.append(scope)
    return tuple(scopes)


def normalize_tool_group_keys(value: Iterable[Any] | Any) -> tuple[str, ...]:
    """把外部传入的工具组 key 归一化为稳定有序元组。"""

    if isinstance(value, str):
        raw_items: Iterable[Any] = [value]
    elif isinstance(value, Iterable):
        raw_items = value
    else:
        raw_items = []

    result: list[str] = []
    for item in raw_items:
        normalized = str(item or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)


def build_tool_disclosure_context(
    *,
    metadata: dict[str, Any] | None,
    scope: Any,
    session_factory: async_sessionmaker[AsyncSession],
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    supports_image_input: bool | None = None,
) -> str:
    """构造内容助手工具可见性说明，追加到统一 Agent 上下文。"""

    _ = (metadata, scope, session_factory, agent_config)
    image_line = (
        "当前模型支持图片输入；如果用户配置开启，页面截图视觉工具可见。"
        if supports_image_input
        else "当前模型不支持图片输入；页面截图视觉工具不会进入本轮工具列表。"
    )
    return "\n".join(
        [
            "当前已直接启用内容助手配置允许的业务工具；工具不再按 workspace/project/page/component 范围分组裁剪。",
            image_line,
            "目标明确且工具可见时，直接调用相应工具；仅在缺少必要业务信息、目标对象不明确或执行路径会导致不同业务结果时向用户提问。平台会处理工具确认和暂停流程。",
        ]
    )
