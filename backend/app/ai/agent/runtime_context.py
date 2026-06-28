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
    project_id: int | None = None
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
        "当前业务范围如下：",
        f"- 范围类型：{runtime_context.scope_type}",
        f"- 工作空间 ID：{runtime_context.workspace_id}",
        f"- 项目 ID：{runtime_context.project_id or '（无）'}",
        f"- 页面 ID：{runtime_context.page_id or '（无）'}",
        f"- 组件 ID：{runtime_context.component_id or '（无）'}",
        f"- 来源：{runtime_context.source}",
    ]
    if runtime_context.page_width is not None and runtime_context.page_height is not None:
        lines.extend(
            [
                f"- 当前页面画布尺寸（page_width / page_height）：{runtime_context.page_width} x {runtime_context.page_height} px",
                f"- {build_base_font_scale_note(runtime_context.base_font_size)}",
                "- 页面和整页组件应按真实画布编写 Vue 与 Tailwind；可使用 Tailwind 语义类，也可在需要精确版式时使用 px、rem 或 Tailwind arbitrary values。",
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
    if runtime_context.suggested_components:
        lines.extend(
            [
                "- 项目建议组件：",
                "以下为项目建议组件摘要；当任务需要选择页面组件、内容组件或原子组件时，建议优先考虑这些组件，不合适时可以查询其他工作空间组件。",
                "组件摘要不能替代使用契约；生成 import、确认 props/slots/preview_schema 或组件版本前，必须调用组件读取工具获取精确信息。",
            ]
        )
        for component in runtime_context.suggested_components:
            lines.append(
                "  - "
                f"component_code={component.get('code')}，"
                f"name={component.get('name')}，"
                f"import_name={component.get('import_name')}，"
                f"component_type={component.get('component_type')}，"
                f"description={component.get('summary') or '（未填写）'}，"
                f"current_version_no={component.get('current_version_no')}"
            )
    if runtime_context.suggested_reference_assets:
        lines.extend(
            [
                "- 项目建议引用资源：",
                "以下为项目建议引用资源；当任务需要使用资源素材时，建议优先考虑这些资源，不合适时可以使用其他资源或询问用户。",
            ]
        )
        for asset in runtime_context.suggested_reference_assets:
            lines.append(
                "  - "
                f"id={asset.get('id')}，"
                f"name={asset.get('name')}，"
                f"original_name={asset.get('original_name')}，"
                f"asset_type={asset.get('asset_type')}，"
                f"description={asset.get('description') or '（未填写）'}，"
                f"content_editable={asset.get('content_editable')}"
            )
    if runtime_context.page_id is not None:
        lines.extend(
            [
                f"- 页面标题：{runtime_context.page_title or '（未知）'}",
                f"- 页面描述：{runtime_context.page_summary or '（未填写）'}",
                f"- 演讲者备注：{runtime_context.page_speaker_notes or '（未填写）'}",
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
