"""文件功能：聚合仍独立运行的智能体工具定义，并提供统一装配入口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(slots=True)
class ComponentManagerToolRegistry:
    """根据当前后端会话工厂构建组件助手工具集。"""

    session_factory: async_sessionmaker[AsyncSession]

    def build_tools(self) -> list[Any]:
        """返回工作空间组件库读写工具列表。"""

        from app.ai.tool_specs import COMPONENT_MANAGER_AGENT_ID, build_agent_tools_from_group_specs

        return build_agent_tools_from_group_specs(
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            session_factory=self.session_factory,
        )


@dataclass(slots=True)
class ResourceManagerToolRegistry:
    """根据当前后端会话工厂构建资源助手工具集。"""

    session_factory: async_sessionmaker[AsyncSession]

    def build_tools(self) -> list[Any]:
        """返回工作空间资源库读写工具列表。"""

        from app.ai.tool_specs import RESOURCE_MANAGER_AGENT_ID, build_agent_tools_from_group_specs

        return build_agent_tools_from_group_specs(
            agent_id=RESOURCE_MANAGER_AGENT_ID,
            session_factory=self.session_factory,
        )
