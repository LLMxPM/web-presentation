"""文件功能：汇总智能体工具共享的上下文校验、Diff/Edits 处理与导入语句工具。"""

from app.ai.tools.shared.component_import import build_component_import_usage
from app.ai.tools.shared.context import get_page_or_raise, resolve_tool_context
from app.ai.tools.shared.page_patch import apply_unified_diff, apply_unified_diff_with_repair, build_unified_diff
from app.ai.tools.shared.preview_schema_argument import (
    allow_preview_schema_object_parameter,
    normalize_preview_schema_argument,
)
from app.ai.tools.shared.source_edits import (
    SourceEditApplyResult,
    SourceEditInput,
    SourceEditPayload,
    apply_source_edits,
    build_source_edits_diff,
    calculate_source_hash,
)

__all__ = [
    "allow_preview_schema_object_parameter",
    "apply_unified_diff",
    "apply_unified_diff_with_repair",
    "apply_source_edits",
    "build_component_import_usage",
    "build_source_edits_diff",
    "build_unified_diff",
    "calculate_source_hash",
    "get_page_or_raise",
    "normalize_preview_schema_argument",
    "resolve_tool_context",
    "SourceEditApplyResult",
    "SourceEditInput",
    "SourceEditPayload",
]
