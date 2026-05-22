"""文件功能：维护当前仓库内可供 Editor 使用的统一 Agent 描述与实例注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID, AgentRuntimeContext
from app.ai.agent_factory import AIAgentFactory
from app.ai.agent_catalog import list_agent_catalog_entries
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig
from app.core.exceptions import AppException


@dataclass(slots=True, frozen=True)
class RegisteredAgentDescriptor:
    """描述一个已在后端注册的 Agent。"""

    id: str
    name: str
    icon: str
    summary: str
    default_session_name: str
    capabilities: tuple[str, ...]
    scope_type: str
    entry_kind: str = "agent"
    llm_slot: str | None = None


class AgentRegistry:
    """封装统一 Agent 描述信息与动态构造入口。"""

    def __init__(self, agent_factory: AIAgentFactory) -> None:
        self._agent_factory = agent_factory
        self._descriptors = {
            catalog.id: RegisteredAgentDescriptor(
                id=catalog.id,
                name=catalog.name,
                icon=catalog.icon,
                summary=catalog.summary,
                default_session_name=catalog.default_session_name,
                capabilities=catalog.capabilities,
                scope_type=catalog.scope_type,
                entry_kind=catalog.entry_kind,
                llm_slot=catalog.llm_slot,
            )
            for catalog in list_agent_catalog_entries()
        }

    def list_descriptors(self) -> list[RegisteredAgentDescriptor]:
        """返回当前已开放给 Editor 的 Agent 描述列表。"""

        return list(self._descriptors.values())

    def get_descriptor(self, agent_id: str) -> RegisteredAgentDescriptor:
        """按 agent_id 读取描述；未注册时抛出标准异常。"""

        descriptor = self._descriptors.get(agent_id)
        if descriptor is None:
            raise AppException(status_code=404, code="AI_AGENT_NOT_FOUND", detail="指定智能体不存在。")
        return descriptor

    def build_agent(
        self,
        *,
        agent_id: str,
        model: Any,
        runtime_context: AgentRuntimeContext,
        session_metadata: dict[str, Any] | None = None,
        agent_config: EffectiveAgentRuntimeConfig | None = None,
        component_model: Any | None = None,
        component_agent_config: EffectiveAgentRuntimeConfig | None = None,
        resource_model: Any | None = None,
        resource_agent_config: EffectiveAgentRuntimeConfig | None = None,
        num_history_messages: int | None = None,
        max_tool_calls_from_history: int = 4,
        enable_session_summaries: bool = False,
        add_session_summary_to_context: bool = False,
    ) -> Any:
        """按 agent_id 和动态模型配置构造可执行的 Agno Agent。"""

        descriptor = self.get_descriptor(agent_id)
        if descriptor.id == AGENT_COORDINATOR_AGENT_ID:
            return self._agent_factory.create_agent_coordinator(
                model=model,
                runtime_context=runtime_context,
                session_metadata=session_metadata,
                agent_config=agent_config,
                component_model=component_model,
                component_agent_config=component_agent_config,
                resource_model=resource_model,
                resource_agent_config=resource_agent_config,
                num_history_messages=num_history_messages,
                max_tool_calls_from_history=max_tool_calls_from_history,
                enable_session_summaries=enable_session_summaries,
                add_session_summary_to_context=add_session_summary_to_context,
            )
        if descriptor.id == COMPONENT_MANAGER_AGENT_ID:
            return self._agent_factory.create_component_manager(
                model=model,
                runtime_context=runtime_context,
                agent_config=agent_config,
                num_history_messages=num_history_messages,
                max_tool_calls_from_history=max_tool_calls_from_history,
                enable_session_summaries=enable_session_summaries,
                add_session_summary_to_context=add_session_summary_to_context,
            )
        if descriptor.id == RESOURCE_MANAGER_AGENT_ID:
            return self._agent_factory.create_resource_manager(
                model=model,
                runtime_context=runtime_context,
                agent_config=agent_config,
                num_history_messages=num_history_messages,
                max_tool_calls_from_history=max_tool_calls_from_history,
                enable_session_summaries=enable_session_summaries,
                add_session_summary_to_context=add_session_summary_to_context,
            )
        raise AppException(status_code=404, code="AI_AGENT_NOT_FOUND", detail="指定智能体不存在。")
