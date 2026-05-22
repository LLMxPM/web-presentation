"""文件功能：验证代码检查工具入口参数归一化逻辑。"""

from __future__ import annotations

import json

from app.ai.tools.shared import normalize_preview_schema_argument


def test_normalize_preview_schema_argument_should_accept_string_dict_and_none() -> None:
    """preview_schema 工具入参应兼容对象字符串、JSON 对象和空值。"""

    schema = {"props": {"title": {"type": "string", "default": "年度汇报"}}, "presets": []}

    assert normalize_preview_schema_argument(None) is None
    assert normalize_preview_schema_argument("{}") == "{}"
    assert json.loads(normalize_preview_schema_argument(schema) or "{}") == schema
