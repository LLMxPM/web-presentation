"""文件功能：提供组件 previewSchema 的文本归一化与 JSON 对象校验辅助函数。"""

from __future__ import annotations

import json
from typing import Any

from app.core.exceptions import AppException
from app.core.runtime_module_policy import (
    is_runtime_public_local_component_module,
    parse_workspace_component_import_path,
)


def normalize_component_preview_schema_text(schema_text: str | None) -> str | None:
    """归一化 previewSchema 文本；空白输入会被视为未配置。"""

    if schema_text is None:
        return None
    normalized_text = str(schema_text).strip()
    return normalized_text or None


def validate_component_preview_schema_text(schema_text: str | None) -> str | None:
    """校验并格式化 previewSchema 文本，确保其为合法 JSON 对象。"""

    normalized_text = normalize_component_preview_schema_text(schema_text)
    if normalized_text is None:
        return None

    parsed_schema = _parse_component_preview_schema_object(normalized_text)
    return json.dumps(parsed_schema, ensure_ascii=False, indent=2)


def parse_component_preview_schema_text(schema_text: str | None) -> dict[str, Any] | None:
    """将 previewSchema 文本解析为 Python 字典；空值返回 None。"""

    normalized_text = normalize_component_preview_schema_text(schema_text)
    if normalized_text is None:
        return None
    return _parse_component_preview_schema_object(normalized_text)


def _parse_component_preview_schema_object(schema_text: str) -> dict[str, Any]:
    """解析 previewSchema JSON 文本，并确保根节点为对象。"""

    try:
        parsed_value = json.loads(schema_text)
    except json.JSONDecodeError as error:
        raise AppException(
            status_code=400,
            code="COMPONENT_PREVIEW_SCHEMA_INVALID",
            detail=f"previewSchema 必须是合法 JSON：{error.msg}",
        ) from error

    if not isinstance(parsed_value, dict):
        raise AppException(
            status_code=400,
            code="COMPONENT_PREVIEW_SCHEMA_INVALID",
            detail="previewSchema 必须是 JSON 对象。",
        )
    _validate_slot_component_references(parsed_value)
    return parsed_value


def _validate_slot_component_references(schema: dict[str, Any]) -> None:
    """校验 slots/presets 中的 component 节点只能引用 Runtime Kit 或工作空间组件。"""

    slots_value = schema.get("slots")
    if isinstance(slots_value, dict):
        for slot_field in slots_value.values():
            if isinstance(slot_field, dict):
                _validate_slot_node_list(slot_field.get("default"))

    presets_value = schema.get("presets")
    if isinstance(presets_value, list):
        for preset in presets_value:
            if not isinstance(preset, dict):
                continue
            preset_slots = preset.get("slots")
            if not isinstance(preset_slots, dict):
                continue
            for slot_nodes in preset_slots.values():
                _validate_slot_node_list(slot_nodes)


def _validate_slot_node_list(slot_nodes: Any) -> None:
    """递归校验 slot 节点数组，防止预览 schema 绕过源码 import 边界。"""

    if slot_nodes is None:
        return
    if not isinstance(slot_nodes, list):
        raise AppException(
            status_code=400,
            code="COMPONENT_PREVIEW_SCHEMA_INVALID",
            detail="previewSchema 的 slot 默认值必须是节点数组。",
        )
    for node in slot_nodes:
        _validate_slot_node(node)


def _validate_slot_node(node: Any) -> None:
    """校验单个 slot 节点及其子节点。"""

    if not isinstance(node, dict):
        raise AppException(
            status_code=400,
            code="COMPONENT_PREVIEW_SCHEMA_INVALID",
            detail="previewSchema 的 slot 节点必须是 JSON 对象。",
        )

    node_type = node.get("type")
    if node_type == "component":
        component_import_path = str(node.get("component") or "").strip()
        if not _is_allowed_slot_component(component_import_path):
            raise AppException(
                status_code=400,
                code="COMPONENT_PREVIEW_SCHEMA_INVALID",
                detail=(
                    "previewSchema 的 slot.component 只能引用 @runtime-kit 清单中的版本化组件"
                    "或 @workspace-components/<component_code>/v/<version_no>。"
                ),
            )
        if "children" in node:
            _validate_slot_node_list(node.get("children"))
        return

    if node_type in {"text", "html"}:
        return

    raise AppException(
        status_code=400,
        code="COMPONENT_PREVIEW_SCHEMA_INVALID",
        detail="previewSchema 的 slot 节点 type 仅支持 text、html、component。",
    )


def _is_allowed_slot_component(component_import_path: str) -> bool:
    """判断 slot.component 是否属于允许的公开导入路径。"""

    if not component_import_path:
        return False
    if is_runtime_public_local_component_module(component_import_path):
        return True
    return parse_workspace_component_import_path(component_import_path) is not None
