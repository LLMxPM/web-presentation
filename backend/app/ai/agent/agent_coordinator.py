"""文件功能：定义内容助手 Team 入口，直接启用配置工具并按需调用成员助手。"""

from __future__ import annotations

from typing import Any

from agno.db.base import BaseDb
from agno.team import Team, TeamMode

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.agent.system_message_localizer import localize_coordinator_team_system_message
from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import (
    EffectiveAgentRuntimeConfig,
    build_effective_description,
    build_effective_instructions,
)
from app.ai.tools.disclosure import build_tool_disclosure_context, build_unified_agent_tools
from app.core.config import get_settings

AGENT_COORDINATOR_AGENT_ID = "agent-coordinator"


def build_agent_coordinator_agent(
    *,
    agno_db: BaseDb | Any,
    session_factory: Any,
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
) -> Team:
    """构建内容助手 Team，保留旧函数名以兼容现有调用点。"""

    return build_agent_coordinator_team(
        agno_db=agno_db,
        session_factory=session_factory,
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


def build_agent_coordinator_team(
    *,
    agno_db: BaseDb | Any,
    session_factory: Any,
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
) -> Team:
    """构建内容助手 Team，由内容助手主执行并按需调用组件助手和资源助手。"""

    settings = get_settings()
    catalog = get_agent_catalog_entry(AGENT_COORDINATOR_AGENT_ID)
    if catalog is None:
        raise RuntimeError("agent-coordinator catalog is not initialized.")
    from app.ai.agent.component_manager import build_component_manager_agent
    from app.ai.agent.resource_manager import build_resource_manager_agent

    resolved_session_metadata = session_metadata or {}
    supports_image_input = bool(resolved_session_metadata.get("model_supports_image_input", False))
    component_member = build_component_manager_agent(
        agno_db=agno_db,
        session_factory=session_factory,
        model=component_model if component_model is not None else model,
        runtime_context=runtime_context,
        agent_config=component_agent_config,
        num_history_messages=num_history_messages,
        max_tool_calls_from_history=max_tool_calls_from_history,
        enable_session_summaries=enable_session_summaries,
        add_session_summary_to_context=add_session_summary_to_context,
    )
    resource_member = build_resource_manager_agent(
        agno_db=agno_db,
        session_factory=session_factory,
        model=resource_model if resource_model is not None else model,
        runtime_context=runtime_context,
        agent_config=resource_agent_config,
        num_history_messages=num_history_messages,
        max_tool_calls_from_history=max_tool_calls_from_history,
        enable_session_summaries=enable_session_summaries,
        add_session_summary_to_context=add_session_summary_to_context,
    )
    team = Team(
        id=AGENT_COORDINATOR_AGENT_ID,
        name=catalog.name,
        description=build_effective_description(catalog, agent_config),
        role=catalog.role,
        mode=TeamMode.coordinate,
        members=[component_member, resource_member],
        model=model,
        db=agno_db,
        add_history_to_context=True,
        num_history_messages=num_history_messages,
        num_history_runs=None,
        max_tool_calls_from_history=max_tool_calls_from_history,
        enable_session_summaries=enable_session_summaries,
        add_session_summary_to_context=add_session_summary_to_context,
        markdown=True,
        instructions=build_effective_instructions(catalog, agent_config),
        additional_context="\n\n".join(
            [
                build_scope_context_text(runtime_context),
                build_tool_disclosure_context(
                    metadata=session_metadata,
                    scope=runtime_context,
                    session_factory=session_factory,
                    agent_config=agent_config,
                    supports_image_input=supports_image_input,
                ),
            ]
        ),
        tools=build_unified_agent_tools(
            session_factory=session_factory,
            agent_config=agent_config,
            supports_image_input=supports_image_input,
        ),
        add_member_tools_to_context=True,
        share_member_interactions=True,
        stream_member_events=True,
        add_datetime_to_context=True,
        debug_mode=settings.app_reload,
        debug_level=2 if settings.app_reload else 1,
    )
    return localize_coordinator_team_system_message(team)
