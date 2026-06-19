"""文件功能：维护当前仓库内可供 Editor 使用的统一 Agent 描述与实例注册表。"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.agent_catalog import list_agent_catalog_entries
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
    """封装统一 Agent 描述信息。"""

    def __init__(self) -> None:
        """初始化内置 Agent 描述索引。"""

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
