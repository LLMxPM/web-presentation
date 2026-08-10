"""文件功能：定义多智能体运行时共享的业务上下文描述。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.base_font_scale import build_base_font_scale_note


@dataclass(slots=True, frozen=True)
class AgentRuntimeContext:
    """描述一次智能体运行绑定的工作空间、项目、页面或组件范围。"""

    scope_type: str
    workspace_id: int
    source: str
    workspace_name: str | None = None
    work_scope_mode: str = "workspace"
    allowed_project_ids: tuple[int, ...] = ()
    allowed_projects: tuple[tuple[int, str], ...] = ()
    focus_version: int = 0
    project_id: int | None = None
    project_name: str | None = None
    page_id: int | None = None
    component_id: int | None = None
    page_width: int | None = None
    page_height: int | None = None
    base_font_size: str | None = None
    style_spec_markdown: str | None = None
    page_title: str | None = None
    page_summary: str | None = None
    page_speaker_notes: str | None = None
    page_code: str | None = None
    page_content: str | None = None
    file_type: str | None = None
    component_code: str | None = None
    component_name: str | None = None
    suggested_components: tuple[dict[str, Any], ...] = ()
    suggested_reference_assets: tuple[dict[str, Any], ...] = ()


def build_scope_context_text(runtime_context: AgentRuntimeContext) -> str:
    """把泛化业务范围格式化为可追加给智能体的上下文说明。"""

    lines = [
        "本轮不可变业务焦点如下：",
        f"- 范围类型：{runtime_context.scope_type}",
        f"- 工作空间 ID：{runtime_context.workspace_id}",
        f"- 工作空间名称：{runtime_context.workspace_name or '（未知）'}",
        f"- 项目 ID：{runtime_context.project_id or '（无）'}",
        f"- 项目名称：{runtime_context.project_name or '（无）'}",
        f"- 页面 ID：{runtime_context.page_id or '（无）'}",
        f"- 页面名称：{runtime_context.page_title or '（无）'}",
        f"- 组件 ID：{runtime_context.component_id or '（无）'}",
        f"- 组件名称：{runtime_context.component_name or '（无）'}",
        f"- 来源：{runtime_context.source}",
        f"- 项目工作集模式：{runtime_context.work_scope_mode}",
        f"- 允许的项目 ID：{list(runtime_context.allowed_project_ids) if runtime_context.work_scope_mode == 'selected_projects' else '工作空间内全部项目'}",
        f"- 允许的项目名称与 ID：{[{'id': item[0], 'name': item[1]} for item in runtime_context.allowed_projects] if runtime_context.work_scope_mode == 'selected_projects' else '工作空间内全部项目'}",
        f"- 焦点版本：{runtime_context.focus_version}",
    ]
    if runtime_context.page_width is not None and runtime_context.page_height is not None:
        lines.extend(
            [
                f"- 当前页面画布尺寸（page_width / page_height）：{runtime_context.page_width} x {runtime_context.page_height} px",
                f"- {build_base_font_scale_note(runtime_context.base_font_size)}",
                "- 页面和整页组件应按真实画布编写 Vue 与 Tailwind；可使用 Tailwind 语义类，也可在需要精确版式时使用 px、rem 或 Tailwind arbitrary values。",
                "- 本项目布局数值基线（安全边距、模块间距、字号层级、分栏、内容密度、页面类型约定）位于项目样式规范，使用 get_entity 的 configuration 视图读取；编写或改写页面时应连同上方画布尺寸与基础字号一并遵循。",
            ]
        )
    else:
        lines.append(
            "- 本轮未注入画布尺寸与基础字号；确定目标项目后，写入页面或页面组件前先用 get_entity 读取该项目 configuration 取得画布尺寸、基础字号、样式规范和建议组件。"
        )
    lines.extend(
        [
            "项目样式、建议组件、建议资源、路由和页面源码不会预注入；集合使用 list_entities，单项详情、源码或结构化视图使用 get_entity 显式读取。查询只返回 active 对象，归档内容不可读取或恢复。",
            "跨焦点读取允许；跨焦点写入会逐次要求用户确认。所有写入必须使用明确 ID，名称只用于搜索。",
            "你不得使用无 ID 的‘当前项目’或‘当前页面’，也不得假设存在任何未通过工具返回的信息。",
        ]
    )
    return "\n".join(lines)
