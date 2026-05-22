"""文件功能：声明 AI Agent 包，并暴露统一智能体构建入口。"""

from app.ai.agent.agent_coordinator import AGENT_COORDINATOR_AGENT_ID, build_agent_coordinator_agent, build_agent_coordinator_team
from app.ai.agent.component_manager import COMPONENT_MANAGER_AGENT_ID
from app.ai.agent.resource_manager import RESOURCE_MANAGER_AGENT_ID, build_resource_manager_agent
from app.ai.agent.runtime_context import AgentRuntimeContext

__all__ = [
    "AGENT_COORDINATOR_AGENT_ID",
    "COMPONENT_MANAGER_AGENT_ID",
    "RESOURCE_MANAGER_AGENT_ID",
    "AgentRuntimeContext",
    "build_agent_coordinator_agent",
    "build_agent_coordinator_team",
    "build_resource_manager_agent",
]
