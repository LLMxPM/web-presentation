"""文件功能：声明页面级 AI 工具包。"""

from app.ai.tools.page.apply_page_edits import build_apply_page_edits_tool
from app.ai.tools.page.get_page_content import build_get_page_content_tool
from app.ai.tools.page.get_page_screenshot import build_get_page_screenshot_tool

__all__ = [
    "build_apply_page_edits_tool",
    "build_get_page_content_tool",
    "build_get_page_screenshot_tool",
]
