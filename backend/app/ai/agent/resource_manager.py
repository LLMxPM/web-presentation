"""文件功能：定义资源助手的标识、提示词与资源库工具装配方式。"""

from __future__ import annotations

from typing import Any

from agno.agent import Agent
from agno.db.base import BaseDb

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import (
    EffectiveAgentRuntimeConfig,
    apply_tool_runtime_config,
    build_effective_description,
    build_effective_instructions,
)
from app.ai.tools import ResourceManagerToolRegistry
from app.core.config import get_settings

RESOURCE_MANAGER_AGENT_ID = "resource-manager"


def build_resource_manager_agent(
    *,
    agno_db: BaseDb | Any,
    session_factory: Any,
    model: Any,
    runtime_context: AgentRuntimeContext,
    agent_config: EffectiveAgentRuntimeConfig | None = None,
    num_history_messages: int | None = None,
    max_tool_calls_from_history: int = 4,
    enable_session_summaries: bool = False,
    add_session_summary_to_context: bool = False,
) -> Agent:
    """构建资源助手，负责工作空间资源库内容与归档管理。"""

    settings = get_settings()
    catalog = get_agent_catalog_entry(RESOURCE_MANAGER_AGENT_ID)
    if catalog is None:
        raise RuntimeError("resource-manager catalog is not initialized.")
    tool_registry = ResourceManagerToolRegistry(session_factory=session_factory)
    return Agent(
        id=RESOURCE_MANAGER_AGENT_ID,
        name=catalog.name,
        role=catalog.role,
        description=build_effective_description(catalog, agent_config),
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
        additional_context=build_scope_context_text(runtime_context),
        tools=apply_tool_runtime_config(
            agent_id=RESOURCE_MANAGER_AGENT_ID,
            tools=tool_registry.build_tools(),
            runtime_config=agent_config,
        ),
        add_datetime_to_context=True,
        debug_mode=settings.app_reload,
        debug_level=2 if settings.app_reload else 1,
    )
