"""文件功能：提供智能体工具 preview_schema 入参归一化与参数 schema 修正辅助。"""

from __future__ import annotations

import json
from typing import Any


def normalize_preview_schema_argument(preview_schema: str | dict[str, Any] | None) -> str | None:
    """归一化工具入参中的 preview_schema，允许模型传 JSON 对象或对象字符串。"""

    if isinstance(preview_schema, dict):
        return json.dumps(preview_schema, ensure_ascii=False)
    return preview_schema


def allow_preview_schema_object_parameter(tool_item: Any) -> None:
    """修正 Agno 自动生成的 schema，使 preview_schema 可表达任意 JSON 对象。"""

    parameters = getattr(tool_item, "parameters", None)
    if not isinstance(parameters, dict):
        return
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return
    properties["preview_schema"] = {
        "anyOf": [
            {"type": "string"},
            {"type": "object", "additionalProperties": True},
            {"type": "null"},
        ]
    }
