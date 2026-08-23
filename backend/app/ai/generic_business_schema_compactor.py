"""文件功能：把判别式对象 Schema 投影为模型更容易兼容的扁平参数 Schema。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


def compact_generic_operation_branches(
    tool_name: str,
    branches: list[dict[str, Any]],
) -> dict[str, Any]:
    """把通用业务工具的分支合并为扁平 Schema，避免根级 oneOf 与本地 $ref。"""

    _ = tool_name
    return flatten_discriminated_object_branches(branches)


def flatten_discriminated_object_branches(
    branches: list[dict[str, Any]],
) -> dict[str, Any]:
    """合并判别式对象分支，并保留字段枚举、类型和共同必填约束。"""

    if not branches:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    property_names: list[str] = []
    property_schemas: dict[str, list[dict[str, Any]]] = {}
    for branch in branches:
        properties = branch.get("properties")
        if not isinstance(properties, dict):
            continue
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                continue
            if field_name not in property_schemas:
                property_names.append(field_name)
                property_schemas[field_name] = []
            property_schemas[field_name].append(field_schema)

    properties = {
        field_name: _merge_property_schemas(property_schemas[field_name])
        for field_name in property_names
    }
    required = _common_required_fields(branches, property_names)
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def _common_required_fields(
    branches: list[dict[str, Any]],
    property_names: list[str],
) -> list[str]:
    """只保留每个分支都要求的字段，避免扁平 Schema 错误要求条件字段。"""

    required_sets = [
        set(branch.get("required", []))
        for branch in branches
        if isinstance(branch.get("required", []), list)
    ]
    if not required_sets:
        return []
    common = set.intersection(*required_sets)
    return [field_name for field_name in property_names if field_name in common]


def _merge_property_schemas(schemas: list[dict[str, Any]]) -> dict[str, Any]:
    """合并同名字段；判别常量转为 enum，其他差异放入字段级 anyOf。"""

    unique_schemas = _unique_schemas(schemas)
    literal_values = _collect_literal_values(unique_schemas)
    if literal_values is not None:
        merged = deepcopy(unique_schemas[0])
        merged.pop("const", None)
        merged.pop("enum", None)
        merged["type"] = _json_type_for_values(literal_values)
        merged["enum"] = literal_values
        return merged
    if len(unique_schemas) == 1:
        return deepcopy(unique_schemas[0])

    variants = _unique_schemas(
        [
            {
                key: deepcopy(value)
                for key, value in schema.items()
                if key not in {"title", "default"}
            }
            for schema in unique_schemas
        ]
    )
    merged: dict[str, Any] = {"anyOf": variants}
    for key in ("description", "default"):
        value = next((schema.get(key) for schema in unique_schemas if key in schema), None)
        if value is not None:
            merged[key] = deepcopy(value)
    return merged


def _collect_literal_values(schemas: list[dict[str, Any]]) -> list[Any] | None:
    """读取全部为 const/enum 的字段值；普通结构字段返回 None。"""

    values: list[Any] = []
    for schema in schemas:
        if "const" in schema:
            current = [schema["const"]]
        elif isinstance(schema.get("enum"), list):
            current = list(schema["enum"])
        else:
            return None
        for value in current:
            if value not in values:
                values.append(value)
    return values or None


def _json_type_for_values(values: list[Any]) -> str:
    """根据合并后的字面量推导基础 JSON 类型。"""

    if all(isinstance(value, bool) for value in values):
        return "boolean"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return "integer"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return "number"
    if all(isinstance(value, str) for value in values):
        return "string"
    if all(value is None for value in values):
        return "null"
    return "string"


def _unique_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按稳定 JSON 表示去重 Schema，保持首次出现顺序。"""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for schema in schemas:
        fingerprint = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(schema)
    return result
