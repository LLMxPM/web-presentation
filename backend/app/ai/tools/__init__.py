"""文件功能：声明智能体工具包，并暴露统一的工具注册入口。"""

from app.ai.tools.registry import ComponentManagerToolRegistry, ResourceManagerToolRegistry

__all__ = ["ComponentManagerToolRegistry", "ResourceManagerToolRegistry"]
