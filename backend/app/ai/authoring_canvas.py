"""文件功能：根据项目真实展示规格派生面向 Agent 的作者画布尺寸。"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
)

REFERENCE_BASE_FONT_SIZE = 16


@dataclass(slots=True, frozen=True)
class AuthoringCanvasSize:
    """描述智能体写页面代码时使用的逻辑画布尺寸。"""

    authoring_width: int
    authoring_height: int


def resolve_authoring_canvas_size(
    *,
    page_width: int | None,
    page_height: int | None,
    base_font_size: str | None,
) -> AuthoringCanvasSize | None:
    """从项目展示规格派生作者画布尺寸；无项目尺寸时返回 None。"""

    normalized_width = _normalize_positive_int(page_width)
    normalized_height = _normalize_positive_int(page_height)
    if normalized_width is None or normalized_height is None:
        return None

    page_scale = min(normalized_width / DEFAULT_PAGE_WIDTH, normalized_height / DEFAULT_PAGE_HEIGHT)
    font_scale = _parse_base_font_size(base_font_size) / REFERENCE_BASE_FONT_SIZE
    token_scale = page_scale * font_scale
    if token_scale <= 0:
        return None

    return AuthoringCanvasSize(
        authoring_width=_round_half_up(normalized_width / token_scale),
        authoring_height=_round_half_up(normalized_height / token_scale),
    )


def _normalize_positive_int(value: int | None) -> int | None:
    """把页面尺寸归一为正整数。"""

    if value is None:
        return None
    numeric_value = int(value)
    return numeric_value if numeric_value > 0 else None


def _parse_base_font_size(value: str | None) -> int:
    """解析基础字号；异常值按系统默认字号处理。"""

    normalized = str(value or DEFAULT_PROJECT_BASE_FONT_SIZE).strip().lower()
    if normalized.endswith("px"):
        normalized = normalized[:-2].strip()
    if not normalized.isdigit():
        normalized = DEFAULT_PROJECT_BASE_FONT_SIZE.removesuffix("px")
    numeric_value = int(normalized)
    return numeric_value if numeric_value > 0 else REFERENCE_BASE_FONT_SIZE


def _round_half_up(value: float) -> int:
    """按常规四舍五入得到正整数尺寸，避免 Python 银行家舍入影响边界值。"""

    return int(value + 0.5)
