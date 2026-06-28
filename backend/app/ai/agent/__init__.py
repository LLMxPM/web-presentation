"""文件功能：声明 AI Agent 包，并暴露智能体运行上下文与固定标识。"""

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.tool_specs import AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID

__all__ = [
    "AGENT_COORDINATOR_AGENT_ID",
    "COMPONENT_MANAGER_AGENT_ID",
    "RESOURCE_MANAGER_AGENT_ID",
    "AgentRuntimeContext",
]
