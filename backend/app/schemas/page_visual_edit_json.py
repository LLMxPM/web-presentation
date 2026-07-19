"""文件功能：校验页面可视化编辑整块 JSON 值的字节、深度、节点数和有限数值边界。"""

from __future__ import annotations

import json
import math

from pydantic import JsonValue


PAGE_VISUAL_EDIT_MAX_JSON_BYTES = 200_000
PAGE_VISUAL_EDIT_MAX_JSON_DEPTH = 32
PAGE_VISUAL_EDIT_MAX_JSON_NODES = 10_000


def validate_page_visual_edit_json(value: JsonValue) -> JsonValue:
    """校验结构化 JSON 的递归规模；返回原值供 Pydantic field validator 使用。"""

    node_count = 0

    def walk(item: JsonValue, depth: int) -> None:
        """递归统计节点并拒绝过深结构和非有限数值。"""

        nonlocal node_count
        node_count += 1
        if depth > PAGE_VISUAL_EDIT_MAX_JSON_DEPTH:
            raise ValueError("JSON 嵌套深度超过 32。")
        if node_count > PAGE_VISUAL_EDIT_MAX_JSON_NODES:
            raise ValueError("JSON 节点数量超过 10000。")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("JSON 数字必须是有限值。")
        if isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, dict):
            for child in item.values():
                walk(child, depth + 1)

    walk(value, 1)
    payload = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    if len(payload.encode("utf-8")) > PAGE_VISUAL_EDIT_MAX_JSON_BYTES:
        raise ValueError("JSON 值超过 200000 字节上限。")
    return value
