"""文件功能：定义多智能体运行时共享的业务上下文描述。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class AgentRuntimeContext:
    """描述一次智能体运行绑定的工作空间、项目、页面或组件范围。"""

    scope_type: str
    workspace_id: int
    source: str
    project_id: int | None = None
    page_id: int | None = None
    component_id: int | None = None
    authoring_width: int | None = None
    authoring_height: int | None = None
    style_spec_markdown: str | None = None
    page_title: str | None = None
    page_summary: str | None = None
    page_code: str | None = None
    page_content: str | None = None
    file_type: str | None = None
    component_code: str | None = None
    component_name: str | None = None


def build_scope_context_text(runtime_context: AgentRuntimeContext) -> str:
    """把泛化业务范围格式化为可追加给 Agno 的上下文说明。"""

    lines = [
        "当前业务范围如下：",
        f"- 范围类型：{runtime_context.scope_type}",
        f"- 工作空间 ID：{runtime_context.workspace_id}",
        f"- 项目 ID：{runtime_context.project_id or '（无）'}",
        f"- 页面 ID：{runtime_context.page_id or '（无）'}",
        f"- 组件 ID：{runtime_context.component_id or '（无）'}",
        f"- 来源：{runtime_context.source}",
    ]
    if runtime_context.authoring_width is not None and runtime_context.authoring_height is not None:
        lines.extend(
            [
                f"- 当前作者画布尺寸（authoring_width / authoring_height）：{runtime_context.authoring_width} x {runtime_context.authoring_height} px",
                "- 页面和整页组件应按作者画布常规使用 Vue 与 Tailwind；优先使用 text-*、p-*、gap-*、grid/flex，不手算字号或间距。",
            ]
        )
    if str(runtime_context.style_spec_markdown or "").strip():
        lines.extend(
            [
                "- 当前项目样式规范（Markdown 纯文本）：",
                "```markdown",
                str(runtime_context.style_spec_markdown).strip(),
                "```",
            ]
        )
    if runtime_context.page_id is not None:
        lines.extend(
            [
                f"- 页面标题：{runtime_context.page_title or '（未知）'}",
                f"- 页面描述：{runtime_context.page_summary or '（未填写）'}",
                f"- 页面编码：{runtime_context.page_code or '（未知）'}",
                f"- 页面文件类型：{runtime_context.file_type or '（未知）'}",
            ]
        )
    if runtime_context.component_id is not None or runtime_context.component_code:
        lines.extend(
            [
                f"- 组件编码：{runtime_context.component_code or '（未知）'}",
                f"- 组件名称：{runtime_context.component_name or '（未知）'}",
            ]
        )
    lines.append("你不得假设存在任何未通过工具返回的信息。")
    return "\n".join(lines)
