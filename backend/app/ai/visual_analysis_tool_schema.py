"""文件功能：按智能体边界投影 analyze_visuals 模型可见输入 Schema。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def project_visual_analysis_schema(
    schema: dict[str, Any],
    *,
    allow_page_screenshot: bool,
) -> dict[str, Any]:
    """移除资源助手不可访问的页面截图输入分支。"""

    projected = deepcopy(schema)
    if allow_page_screenshot:
        return projected
    _remove_page_screenshot_refs(projected)
    definitions = projected.get("$defs")
    if isinstance(definitions, dict):
        definitions.pop("PageScreenshotVisualInput", None)
    return projected


def _remove_page_screenshot_refs(value: Any) -> None:
    """递归清理指向 PageScreenshotVisualInput 的组合 Schema 分支。"""

    if isinstance(value, dict):
        mapping = value.get("mapping")
        if isinstance(mapping, dict):
            value["mapping"] = {
                key: target
                for key, target in mapping.items()
                if not str(target).endswith("/PageScreenshotVisualInput")
            }
        for key in ("oneOf", "anyOf"):
            branches = value.get(key)
            if isinstance(branches, list):
                value[key] = [branch for branch in branches if not _is_page_screenshot_ref(branch)]
        for child in value.values():
            _remove_page_screenshot_refs(child)
        return
    if isinstance(value, list):
        for child in value:
            _remove_page_screenshot_refs(child)


def _is_page_screenshot_ref(value: Any) -> bool:
    """判断组合分支是否引用页面截图输入模型。"""

    return isinstance(value, dict) and str(value.get("$ref") or "").endswith("/PageScreenshotVisualInput")
