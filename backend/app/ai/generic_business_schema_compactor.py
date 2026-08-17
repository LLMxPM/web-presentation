"""文件功能：压缩通用业务工具的重复判别式 JSON Schema 分支。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


def compact_generic_operation_branches(
    tool_name: str,
    branches: list[dict[str, Any]],
) -> dict[str, Any]:
    """按安全分组压缩通用工具分支，无法证明同形状时保留原始 Schema。"""

    grouped: dict[str, list[dict[str, Any]]] = {}
    ungrouped: list[dict[str, Any]] = []
    for branch in branches:
        group_key = _operation_branch_group_key(tool_name, branch)
        if group_key is None:
            ungrouped.append(branch)
            continue
        grouped.setdefault(group_key, []).append(branch)

    if not any(len(items) > 1 for items in grouped.values()):
        return {"type": "object", "oneOf": branches}

    definitions: dict[str, Any] = {}
    references: list[dict[str, str]] = []
    group_index = 0
    for group_branches in grouped.values():
        compacted = _build_compact_branch(
            tool_name=tool_name,
            group_index=group_index,
            branches=group_branches,
        )
        if compacted is None:
            for branch in group_branches:
                definition_name = f"{tool_name}_operation_{group_index}"
                definitions[definition_name] = branch
                references.append({"$ref": f"#/$defs/{definition_name}"})
                group_index += 1
            continue
        definition_name, definition = compacted
        definitions[definition_name] = definition
        references.append({"$ref": f"#/$defs/{definition_name}"})
        group_index += 1

    for branch in ungrouped:
        definition_name = f"{tool_name}_operation_{group_index}"
        definitions[definition_name] = branch
        references.append({"$ref": f"#/$defs/{definition_name}"})
        group_index += 1

    return {
        "type": "object",
        "$defs": definitions,
        "oneOf": references,
    }


def _operation_branch_group_key(tool_name: str, branch: dict[str, Any]) -> str | None:
    """根据当前分支的实际判别值选择可安全压缩的结构分组。"""

    properties = branch.get("properties")
    if not isinstance(properties, dict):
        return None
    constants = {
        name: value.get("const")
        for name, value in properties.items()
        if isinstance(value, dict) and "const" in value
    }
    if tool_name == "list_entities":
        return f"collection:{constants.get('collection')}"
    if tool_name == "get_entity":
        resource_type = constants.get("resource_type")
        view = constants.get("view")
        if resource_type in {"page", "component"} and view == "version_content":
            return "version_content"
        if resource_type == "runtime_kit":
            return "runtime_detail"
        return f"resource:{resource_type}"
    if tool_name == "create_entity":
        return f"mode:{constants.get('mode')}"
    if tool_name in {"update_entity", "validate_entity"}:
        return f"action:{constants.get('action')}"
    if tool_name == "archive_entity":
        return "all_resources"
    return None


def _normalized_branch(branch: dict[str, Any]) -> dict[str, Any]:
    """移除判别字段 const 后生成结构指纹，避免合并不同字段形状。"""

    normalized = deepcopy(branch)
    properties = normalized.get("properties")
    if isinstance(properties, dict):
        for property_schema in properties.values():
            if isinstance(property_schema, dict):
                property_schema.pop("const", None)
    return normalized


def _build_compact_branch(
    *,
    tool_name: str,
    group_index: int,
    branches: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    """把同形状合法分支合并为带枚举判别字段的本地定义。"""

    if not branches:
        return None
    first = branches[0]
    signature = json.dumps(_normalized_branch(first), ensure_ascii=False, sort_keys=True)
    if any(
        json.dumps(_normalized_branch(branch), ensure_ascii=False, sort_keys=True) != signature
        for branch in branches[1:]
    ):
        return None

    compacted = deepcopy(first)
    properties = compacted.get("properties")
    if not isinstance(properties, dict):
        return None
    first_properties = first.get("properties")
    if not isinstance(first_properties, dict):
        return None

    for field_name, field_schema in first_properties.items():
        if not isinstance(field_schema, dict) or "const" not in field_schema:
            continue
        values = [
            branch["properties"][field_name]["const"]
            for branch in branches
            if isinstance(branch.get("properties"), dict)
            and isinstance(branch["properties"].get(field_name), dict)
            and "const" in branch["properties"][field_name]
        ]
        unique_values = list(dict.fromkeys(values))
        if len(unique_values) <= 1:
            continue
        merged_schema = deepcopy(field_schema)
        merged_schema.pop("const", None)
        merged_schema["type"] = "string"
        merged_schema["enum"] = unique_values
        properties[field_name] = merged_schema

    definition_name = f"{tool_name}_operation_{group_index}"
    return definition_name, compacted
