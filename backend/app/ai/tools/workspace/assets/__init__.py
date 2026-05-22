"""文件功能：声明工作空间资源类 AI 工具包。"""

from app.ai.tools.workspace.assets.list_workspace_font_assets import build_list_workspace_font_assets_tool
from app.ai.tools.workspace.assets.list_workspace_icon_assets import build_list_workspace_icon_assets_tool
from app.ai.tools.workspace.assets.list_workspace_render_assets import build_list_workspace_render_assets_tool
from app.ai.tools.workspace.assets.list_workspace_resource_tags import build_list_workspace_resource_tags_tool

__all__ = [
    "build_list_workspace_font_assets_tool",
    "build_list_workspace_icon_assets_tool",
    "build_list_workspace_render_assets_tool",
    "build_list_workspace_resource_tags_tool",
]
