"""文件功能：合成用户级智能体配置，并把有效配置应用到 Agno Agent 与工具对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.agent_catalog import AgentCatalogEntry, get_agent_catalog_entry, get_agent_tool_catalog_entry
from app.ai.tool_specs import apply_tool_spec_metadata


@dataclass(slots=True, frozen=True)
class EffectiveToolRuntimeConfig:
    """描述某个工具在当前用户配置下的运行时状态。"""

    key: str
    enabled: bool
    configurable: bool
    description_override: str | None = None
    instructions_override: str | None = None


@dataclass(slots=True, frozen=True)
class EffectiveAgentRuntimeConfig:
    """描述某个 Agent 在当前用户配置下的运行时有效配置。"""

    agent_id: str
    description_override: str | None
    prompt_override: str | None
    tool_configs: dict[str, EffectiveToolRuntimeConfig]

    @property
    def description_customized(self) -> bool:
        """判断当前 Agent 是否使用了用户描述覆盖。"""

        return bool(self.description_override)

    @property
    def prompt_customized(self) -> bool:
        """判断当前 Agent 是否使用了用户业务补充提示词。"""

        return bool(self.prompt_override)

    @property
    def enabled_tool_keys(self) -> tuple[str, ...]:
        """返回当前用户开启的工具 key。"""

        return tuple(key for key, config in self.tool_configs.items() if config.enabled)

    @property
    def disabled_tool_keys(self) -> tuple[str, ...]:
        """返回当前用户关闭的工具 key。"""

        return tuple(key for key, config in self.tool_configs.items() if not config.enabled)


def build_default_runtime_config(agent_id: str) -> EffectiveAgentRuntimeConfig:
    """按内置目录构造默认运行时配置。"""

    catalog = get_agent_catalog_entry(agent_id)
    if catalog is None:
        return EffectiveAgentRuntimeConfig(
            agent_id=agent_id,
            description_override=None,
            prompt_override=None,
            tool_configs={},
        )
    return EffectiveAgentRuntimeConfig(
        agent_id=agent_id,
        description_override=None,
        prompt_override=None,
        tool_configs={
            tool.key: EffectiveToolRuntimeConfig(
                key=tool.key,
                enabled=True,
                configurable=tool.configurable,
            )
            for tool in catalog.tools
        },
    )


def build_effective_instructions(
    catalog: AgentCatalogEntry,
    runtime_config: EffectiveAgentRuntimeConfig | None,
) -> list[str]:
    """合成平台底线提示词与用户补充业务提示词。"""

    prompt_override = runtime_config.prompt_override if runtime_config is not None else None
    instructions = list(catalog.system_instructions)
    if prompt_override:
        instructions.append(prompt_override)
    return instructions


def build_effective_description(
    catalog: AgentCatalogEntry,
    runtime_config: EffectiveAgentRuntimeConfig | None,
) -> str:
    """合成当前 Agent 在运行时应暴露给 Agno 的描述。"""

    description_override = runtime_config.description_override if runtime_config is not None else None
    return description_override or catalog.description


def is_tool_enabled(
    *,
    agent_id: str,
    tool_key: str,
    runtime_config: EffectiveAgentRuntimeConfig | None,
) -> bool:
    """判断工具是否应进入当前 Agent 可见工具列表。"""

    catalog_entry = get_agent_tool_catalog_entry(agent_id, tool_key)
    if catalog_entry is not None and not catalog_entry.configurable:
        return True
    if runtime_config is None:
        return True
    tool_config = runtime_config.tool_configs.get(tool_key)
    return True if tool_config is None else tool_config.enabled


def apply_tool_runtime_config(
    *,
    agent_id: str,
    tools: list[Any],
    runtime_config: EffectiveAgentRuntimeConfig | None,
) -> list[Any]:
    """过滤关闭的工具，并把用户覆盖的工具说明写入 Agno Function 对象。"""

    result: list[Any] = []
    for tool_item in apply_tool_spec_metadata(agent_id=agent_id, tools=tools):
        tool_key = str(getattr(tool_item, "name", "") or "")
        if not tool_key:
            result.append(tool_item)
            continue
        if not is_tool_enabled(agent_id=agent_id, tool_key=tool_key, runtime_config=runtime_config):
            continue

        tool_config = runtime_config.tool_configs.get(tool_key) if runtime_config is not None else None
        if tool_config is not None:
            if tool_config.description_override:
                setattr(tool_item, "description", tool_config.description_override)
            if tool_config.instructions_override:
                setattr(tool_item, "instructions", tool_config.instructions_override)
        result.append(tool_item)
    return result
