"""文件功能：迁移至 Renderer 的页面布局与组件场景诊断脚本单一事实源。"""

from __future__ import annotations

from wp_renderer.engine.component_layout_script import build_component_render_layout_script
from wp_renderer.engine.page_render_layout_script import build_page_render_layout_script

LAYOUT_ANALYSIS_SCHEMA_VERSION = 3
COMPONENT_SCENARIO_LIMIT = 16

__all__ = [
    "LAYOUT_ANALYSIS_SCHEMA_VERSION",
    "COMPONENT_SCENARIO_LIMIT",
    "build_page_render_layout_script",
    "build_component_render_layout_script",
]
