"""文件功能：统一解析 Pydantic AI 工具参数，保证运行态落库使用对象结构。"""

from __future__ import annotations

import json
from typing import Any


def parse_tool_arguments(value: Any) -> dict[str, Any] | None:
    """将字典或 JSON 对象字符串解析为工具参数；空值和非对象结构返回 None。"""

    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return dict(parsed) if isinstance(parsed, dict) else None
