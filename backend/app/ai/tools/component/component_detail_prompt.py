"""文件功能：把组件详情渲染为智能体可精确编辑的源码提示文本。"""

from __future__ import annotations

from app.ai.tools.shared import calculate_source_hash
from app.schemas.component import WorkspaceComponentItem


def build_component_detail_prompt(component: WorkspaceComponentItem) -> str:
    """把组件元数据和源码渲染为适合 LLM 读取和生成 edits 的纯文本。

    输入是组件详情响应模型；输出包含原始源码和草稿锁字段。
    """

    summary_text = component.summary or "（未填写）"
    draft_hash = calculate_source_hash(component.content)
    preview_schema_lines = _build_preview_schema_lines(component.preview_schema)

    return "\n".join(
        [
            f"组件 ID：{component.id}",
            f"组件编码：{component.code}",
            f"组件名称：{component.name}",
            f"源码引用名：{component.import_name}",
            f"组件类型：{component.component_type.value}",
            f"组件描述：{summary_text}",
            f"文件类型：{component.file_type.value}",
            f"current_version_no（当前发布版本号）：{component.current_version_no}",
            f"base_published_version_no（草稿基线版本号）：{component.draft_base_version_no}",
            f"draft_hash（草稿内容指纹）：{draft_hash}",
            f"存在未发布修改：{_format_bool(component.has_unpublished_changes)}",
            *preview_schema_lines,
            "",
            "以下是当前组件完整源码。",
            "生成 edits 时，直接复制源码中的真实片段作为 old_text、anchor_text 或 content。",
            "调用组件 edits 工具时，base_draft_hash 使用上方 draft_hash，base_published_version_no 使用上方同名字段。",
            "",
            "源码：",
            "```text",
            component.content,
            "```",
        ]
    )


def _build_preview_schema_lines(preview_schema: str | None) -> list[str]:
    """按是否存在 preview schema 渲染组件预览配置说明。"""

    if preview_schema is None or preview_schema == "":
        return ["预览 schema：未填写"]
    return ["预览 schema：", "```json", preview_schema, "```"]


def _format_bool(value: bool) -> str:
    """把布尔值转换为中文可读文本。"""

    return "是" if value else "否"
