"""文件功能：按操作手册为通用业务工具投影模型可见的判别式顶层参数 Schema。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from app.ai.generic_business_schema_compactor import compact_generic_operation_branches


GENERIC_BUSINESS_TOOL_KEYS = frozenset(
    {
        "get_operation_guide",
        "list_entities",
        "get_entity",
        "create_entity",
        "update_entity",
        "archive_entity",
        "validate_entity",
        "execute_action",
    }
)

_DEFERRED_DETAIL_FIELDS = frozenset({"filters", "lookup", "options", "payload"})


def project_generic_business_tool_schema(
    tool_name: str,
    source_schema: dict[str, Any],
    guides: Iterable[Any],
) -> dict[str, Any]:
    """投影合法顶层组合，具体业务字段仍由 operation_key 对应手册按需披露。"""

    if tool_name not in GENERIC_BUSINESS_TOOL_KEYS:
        return deepcopy(source_schema)
    guide_items = tuple(guides)
    if tool_name == "get_operation_guide":
        return _project_guide_lookup_schema(source_schema, guide_items)
    branches = [
        _build_operation_branch(source_schema, guide.parameters)
        for guide in guide_items
        if guide.handler_tool_key == tool_name
    ]
    if not branches:
        return deepcopy(source_schema)
    return compact_generic_operation_branches(tool_name, branches)


def _project_guide_lookup_schema(source_schema: dict[str, Any], guides: tuple[Any, ...]) -> dict[str, Any]:
    """把手册定位参数收窄为稳定 operation_key 枚举，同时允许无参数查询索引。"""

    source_property = deepcopy(source_schema.get("properties", {}).get("operation_key", {}))
    description = source_property.get("description") or "稳定操作键；不传时返回全部操作的紧凑索引。"
    return {
        "type": "object",
        "properties": {
            "operation_key": {
                "anyOf": [
                    {"type": "string", "enum": [guide.operation_key for guide in guides]},
                    {"type": "null"},
                ],
                "default": None,
                "description": description,
            }
        },
        "additionalProperties": False,
    }


def _build_operation_branch(
    source_schema: dict[str, Any],
    exact_schema: dict[str, Any],
) -> dict[str, Any]:
    """从精确手册保留判别字段和顶层形状，把复杂对象恢复为常驻宽类型。"""

    source_properties = source_schema.get("properties", {})
    exact_properties = exact_schema.get("properties", {})
    properties: dict[str, Any] = {}
    for field_name, field_schema in exact_properties.items():
        if field_name in _DEFERRED_DETAIL_FIELDS:
            source_field = source_properties.get(field_name)
            properties[field_name] = (
                deepcopy(source_field)
                if isinstance(source_field, dict)
                else {
                    "type": ["object", "null"],
                    "description": "具体字段必须符合 operation_key 对应操作手册。",
                }
            )
            continue
        properties[field_name] = deepcopy(field_schema)
    return {
        "type": "object",
        "properties": properties,
        "required": list(exact_schema.get("required", [])),
        "additionalProperties": False,
    }
