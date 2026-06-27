"""文件功能：提供基础字号相对 Tailwind 默认基准的提示文本格式化能力。"""

from __future__ import annotations

import re

TAILWIND_DEFAULT_BASE_FONT_SIZE_PX = 16
_BASE_FONT_SIZE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*$", re.IGNORECASE)


def build_base_font_scale_note(base_font_size: str | None) -> str:
    """生成基础字号相对 Tailwind 默认基准的倍率说明，供提示词和工具返回复用。"""

    label = str(base_font_size or "").strip() or "（未知）"
    scale = _parse_base_font_scale(label)
    scale_text = (
        f"Tailwind 默认 16px 基准的 {_format_scale(scale)} 倍"
        if scale is not None
        else "Tailwind 默认 16px 基准的倍率未知"
    )
    return (
        f"当前项目基础字号（base_font_size）：{label}，相当于 {scale_text}；"
        "text-*、p-*、m-*、gap-*、space-* 等语义尺度会按该倍率渲染；"
        "直接写 px、rem 或 Tailwind arbitrary values 不参与该倍率。"
    )


def _parse_base_font_scale(base_font_size: str) -> float | None:
    """从基础字号字符串解析相对 Tailwind 默认 16px 的倍率。"""

    match = _BASE_FONT_SIZE_PATTERN.match(base_font_size)
    if not match:
        return None
    numeric_value = float(match.group(1))
    if numeric_value <= 0:
        return None
    return numeric_value / TAILWIND_DEFAULT_BASE_FONT_SIZE_PX


def _format_scale(scale: float) -> str:
    """格式化倍率，避免输出无意义的尾随 0。"""

    return f"{scale:.3f}".rstrip("0").rstrip(".")
