"""文件功能：定义统一智能体可披露的页面源码读取工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agno.run import RunContext
from agno.tools import tool
from agno.tools.function import ToolResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PAGE_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.schemas.page import PageItem
from app.services.page_service import PageService


@dataclass(slots=True, frozen=True)
class PageContentSourceInfo:
    """描述页面源码读取来源，便于模型区分显式目标页与上下文页面。"""

    resolved_from: Literal["argument", "context"]
    context_page_id: int | None
    context_source: str | None
    context_project_id: int | None
    context_workspace_id: int | None


def build_get_page_content_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建页面源码读取工具，支持显式 page_id 或从上下文自动推断。"""

    @tool(show_result=False)
    async def get_page_content(run_context: RunContext, page_id: int | None = None) -> ToolResult:
        """读取页面源码；page_id 为空时读取当前上下文页面。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PAGE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        target_page_id, resolved_from = _resolve_target_page_id(page_id, dependencies)

        async with session_factory() as session:
            page_item = await PageService(session).get(target_page_id)
            _ensure_page_in_context(page_item, dependencies)
            return ToolResult(
                content=build_page_content_prompt(
                    page_item,
                    page_width=_coerce_optional_int(dependencies.get("page_width")),
                    page_height=_coerce_optional_int(dependencies.get("page_height")),
                    base_font_size=_coerce_optional_str(dependencies.get("base_font_size")),
                    source_info=PageContentSourceInfo(
                        resolved_from=resolved_from,
                        context_page_id=_coerce_optional_int(dependencies.get("page_id")),
                        context_source=_coerce_optional_str(dependencies.get("source")),
                        context_project_id=_coerce_optional_int(dependencies.get("project_id")),
                        context_workspace_id=_coerce_optional_int(dependencies.get("workspace_id")),
                    ),
                )
            )

    return get_page_content


def build_page_content_prompt(
    page_item: PageItem,
    *,
    page_width: int | None = None,
    page_height: int | None = None,
    base_font_size: str | None = None,
    source_info: PageContentSourceInfo | None = None,
) -> str:
    """把页面信息渲染为适合 LLM 读取和生成 edits 的纯文本。"""

    file_type = page_item.file_type.value
    page_content = str(page_item.page_content or "")
    summary_text = page_item.summary or "（未填写）"
    speaker_notes_text = page_item.speaker_notes or "（未填写）"
    page_canvas_lines = []
    if page_width is not None and page_height is not None:
        page_canvas_lines = [
            f"当前页面画布尺寸（page_width / page_height）：{page_width} x {page_height} px",
            f"当前项目基础字号（base_font_size）：{base_font_size or '（未知）'}",
            "base_font_size 作用：text-base 等于该值，text-* 字号、p-/m-/gap-/space-* 等 spacing 按 Runtime Tailwind 预设比例派生；page_width/page_height 不参与该换算。",
            "固定尺度说明：直接写 px、rem 或 Tailwind arbitrary values 不会随 base_font_size 自动变化；需要跟随基础字号时使用 Tailwind 语义尺度，或以 base_font_size 为基准计算。",
            "页面排版约束：按真实画布编写；可使用 Tailwind 语义类，也可在需要精确版式时使用 px、rem 或 Tailwind arbitrary values。",
        ]

    return "\n".join(
        [
            *_build_page_source_lines(page_item, source_info),
            "",
            f"页面编码：{page_item.code}",
            f"页面标题：{page_item.title}",
            f"页面描述：{summary_text}",
            f"演讲者备注：{speaker_notes_text}",
            f"文件类型：{file_type}",
            f"当前版本：v{page_item.current_version_no}",
            f"页面状态：{page_item.status.value}",
            *page_canvas_lines,
            "",
            "以下是当前页面完整源码。",
            "生成 edits 时，直接复制源码中的真实片段作为 old_text、anchor_text 或 content。",
            "每个 edit 对象必须包含 type 字段，取值只能是 replace_exact、insert_after 或 rewrite_file。",
            "调用 apply_page_edits 时，page_id 使用上方目标页面 ID，base_version_no 使用上方当前版本号。",
            "",
            "源码：",
            "```text",
            page_content,
            "```",
        ]
    )


def _resolve_target_page_id(
    requested_page_id: int | None,
    dependencies: dict[str, Any],
) -> tuple[int, Literal["argument", "context"]]:
    """解析本次要读取的页面 ID，优先使用工具参数。"""

    if requested_page_id is not None:
        return int(requested_page_id), "argument"

    context_page_id = _coerce_optional_int(dependencies.get("page_id"))
    if context_page_id is None:
        raise AppException(
            status_code=401,
            code="AI_TOOL_SCOPE_REQUIRED",
            detail="当前工具缺少必要上下文字段：page_id。请传入 page_id，或在页面上下文中调用。",
        )
    return context_page_id, "context"


def _ensure_page_in_context(page_item: PageItem, dependencies: dict[str, Any]) -> None:
    """确保显式读取的页面不越过当前工具令牌绑定的工作空间或项目边界。"""

    workspace_id = _coerce_optional_int(dependencies.get("workspace_id"))
    project_id = _coerce_optional_int(dependencies.get("project_id"))
    if workspace_id is not None and page_item.workspace_id != workspace_id:
        raise AppException(
            status_code=403,
            code="AI_TOOL_CONTEXT_MISMATCH",
            detail="目标页面不属于当前工具上下文绑定的工作空间。",
        )
    if project_id is not None and page_item.project_id != project_id:
        raise AppException(
            status_code=403,
            code="AI_TOOL_CONTEXT_MISMATCH",
            detail="目标页面不属于当前工具上下文绑定的项目。",
        )


def _build_page_source_lines(page_item: PageItem, source_info: PageContentSourceInfo | None) -> list[str]:
    """渲染页面来源和目标页元数据，供模型识别读取边界。"""

    resolved_from = "上下文 page_id" if source_info is None or source_info.resolved_from == "context" else "工具参数 page_id"
    lines = [
        "页面源信息：",
        f"- 读取方式：{resolved_from}",
        f"- 目标页面 ID：{page_item.id}",
        f"- 目标工作空间：{page_item.workspace_id or '（无）'} / {page_item.workspace_name or '（未知）'}",
        f"- 目标项目：{page_item.project_id or '（无）'} / {page_item.project_name or '（未知）'}",
    ]
    if source_info is None:
        return lines

    lines.extend(
        [
            f"- 上下文来源：{source_info.context_source or '（未知）'}",
            f"- 上下文页面 ID：{source_info.context_page_id or '（无）'}",
            f"- 上下文工作空间 ID：{source_info.context_workspace_id or '（无）'}",
            f"- 上下文项目 ID：{source_info.context_project_id or '（无）'}",
        ]
    )
    return lines


def _coerce_optional_int(value: Any) -> int | None:
    """把工具依赖中的整数字段安全转换为整数。"""

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_str(value: Any) -> str | None:
    """把上下文字段转换为非空字符串。"""

    normalized = str(value or "").strip()
    return normalized or None
