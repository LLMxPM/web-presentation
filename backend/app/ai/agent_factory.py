"""文件功能：聚合 AI Agent 构建入口，并向外暴露统一的工厂封装。"""

from __future__ import annotations

from typing import Any

from agno.db.base import BaseDb

from app.ai.agent import AgentRuntimeContext, build_agent_coordinator_agent
from app.ai.agent.component_manager import build_component_manager_agent
from app.ai.agent.resource_manager import build_resource_manager_agent
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig


class AIAgentFactory:
    """集中创建后端内嵌的 Agno Agent，避免入口文件堆积初始化细节。"""

    def __init__(self, *, agno_db: BaseDb | Any, session_factory: Any) -> None:
        """初始化 Agent 工厂，并缓存数据库与会话工厂依赖。"""

        self._agno_db = agno_db
        self._session_factory = session_factory

    def create_component_manager(
        self,
        *,
        model: Any,
        runtime_context: AgentRuntimeContext,
        agent_config: EffectiveAgentRuntimeConfig | None = None,
        num_history_messages: int | None = None,
        max_tool_calls_from_history: int = 4,
        enable_session_summaries: bool = False,
        add_session_summary_to_context: bool = False,
    ) -> Any:
        """创建组件助手。"""

        return build_component_manager_agent(
            agno_db=self._agno_db,
            session_factory=self._session_factory,
            model=model,
            runtime_context=runtime_context,
            agent_config=agent_config,
            num_history_messages=num_history_messages,
            max_tool_calls_from_history=max_tool_calls_from_history,
            enable_session_summaries=enable_session_summaries,
            add_session_summary_to_context=add_session_summary_to_context,
        )

    def create_resource_manager(
        self,
        *,
        model: Any,
        runtime_context: AgentRuntimeContext,
        agent_config: EffectiveAgentRuntimeConfig | None = None,
        num_history_messages: int | None = None,
        max_tool_calls_from_history: int = 4,
        enable_session_summaries: bool = False,
        add_session_summary_to_context: bool = False,
    ) -> Any:
        """创建资源助手。"""

        return build_resource_manager_agent(
            agno_db=self._agno_db,
            session_factory=self._session_factory,
            model=model,
            runtime_context=runtime_context,
            agent_config=agent_config,
            num_history_messages=num_history_messages,
            max_tool_calls_from_history=max_tool_calls_from_history,
            enable_session_summaries=enable_session_summaries,
            add_session_summary_to_context=add_session_summary_to_context,
        )

    def create_agent_coordinator(
        self,
        *,
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
        """创建内容助手 Team 入口。"""

        return build_agent_coordinator_agent(
            agno_db=self._agno_db,
            session_factory=self._session_factory,
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
