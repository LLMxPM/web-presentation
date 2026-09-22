"""文件功能：规范化页面布局分析契约，保证成功与不可用路径结构一致。"""

from __future__ import annotations

from typing import Any

from render_contracts.constants import LAYOUT_ANALYSIS_SCHEMA_VERSION

LAYOUT_ANALYSIS_RESULT_KEYS = (
    "text_layouts",
    "item_groups",
    "overflows",
    "spatial_relations",
    "empty_regions",
)

_VALID_ATTENTIONS = frozenset({"none", "review", "likely_issue"})


def empty_layout_analysis(*, message: str = "未发现需要关注的视觉检测结果。", truncated: bool = False) -> dict[str, Any]:
    """返回稳定空布局分析结构。"""

    zeros = {key: 0 for key in LAYOUT_ANALYSIS_RESULT_KEYS}
    return {
        "schema_version": LAYOUT_ANALYSIS_SCHEMA_VERSION,
        "meta": None,
        "summary": {
            "attention": "none",
            "message": message,
            "totals": dict(zeros),
            "returned": dict(zeros),
            "truncated": truncated,
        },
        **{key: [] for key in LAYOUT_ANALYSIS_RESULT_KEYS},
    }


def normalize_layout_analysis(value: object) -> dict[str, Any]:
    """把任意布局分析结果收敛为 schema v3 全量结构。"""

    if not isinstance(value, dict):
        return empty_layout_analysis()
    result_lists = {key: _normalize_dict_list(value.get(key)) for key in LAYOUT_ANALYSIS_RESULT_KEYS}
    raw_summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
    summary = _normalize_layout_summary(raw_summary, result_lists)
    return {
        "schema_version": LAYOUT_ANALYSIS_SCHEMA_VERSION,
        "meta": _normalize_layout_meta(value.get("meta")),
        "summary": summary,
        **result_lists,
    }


def _normalize_dict_list(value: object) -> list[dict[str, Any]]:
    """仅保留对象列表项。"""

    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _coerce_non_negative_int(value: object, fallback: int) -> int:
    """转换为非负整数。"""

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def _coerce_positive_number(value: object) -> float | None:
    """转换为正数尺寸，非法时返回 None。"""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalize_layout_meta(value: object) -> dict[str, Any] | None:
    """规范化画布元数据。"""

    if not isinstance(value, dict):
        return None
    canvas = value.get("canvas_size")
    if not isinstance(canvas, dict):
        return None
    width = _coerce_positive_number(canvas.get("width"))
    height = _coerce_positive_number(canvas.get("height"))
    threshold_scale = _coerce_positive_number(value.get("threshold_scale"))
    if width is None or height is None or threshold_scale is None:
        return None
    return {
        "canvas_size": {"width": width, "height": height},
        "threshold_scale": threshold_scale,
    }


def _normalize_layout_summary(
    value: dict[str, Any],
    result_lists: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """按实际返回清单修正 summary 计数，并保留截断前总数。"""

    raw_totals = value.get("totals") if isinstance(value.get("totals"), dict) else {}
    totals = {
        key: _coerce_non_negative_int(raw_totals.get(key), len(result_lists[key]))
        for key in LAYOUT_ANALYSIS_RESULT_KEYS
    }
    returned = {key: len(result_lists[key]) for key in LAYOUT_ANALYSIS_RESULT_KEYS}
    attention = str(value.get("attention") or "none")
    if attention not in _VALID_ATTENTIONS:
        attention = "none"
    message = str(value.get("message") or "").strip()
    if not message:
        message = (
            "未发现需要关注的视觉检测结果。"
            if attention == "none"
            else "发现需要关注的视觉检测结果。"
        )
    return {
        "attention": attention,
        "message": message,
        "totals": totals,
        "returned": returned,
        "truncated": bool(value.get("truncated"))
        or any(totals[key] > returned[key] for key in LAYOUT_ANALYSIS_RESULT_KEYS),
    }
