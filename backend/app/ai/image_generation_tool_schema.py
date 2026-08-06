"""文件功能：把图片模型能力投影为本轮 generate_image 模型可见参数 Schema。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.image_generation.contracts import ImageModelSpec


def project_generate_image_schema(
    source_schema: dict[str, Any],
    model: ImageModelSpec,
) -> dict[str, Any]:
    """按绑定模型收窄通用工具 Schema，隐藏没有实际业务含义的参数。"""

    schema = deepcopy(source_schema)
    properties = schema.setdefault("properties", {})
    _set_enum(properties, "operation", model.operations)
    _set_enum(properties, "aspect_ratio", model.aspect_ratios)
    _set_enum(properties, "resolution_tier", model.resolution_tiers)

    if model.quality_options in {(), ("auto",)}:
        _remove_property(schema, "quality")
    else:
        _set_enum(properties, "quality", model.quality_options)

    if not model.supports_mask:
        _remove_property(schema, "mask_attachment_id")

    _set_array_max_items(properties.get("reference_attachment_ids"), model.max_reference_images)
    count_schema = properties.get("count")
    if isinstance(count_schema, dict):
        count_schema["maximum"] = model.max_output_count

    return _project_operation_branches(schema, model.operations, supports_mask=model.supports_mask)


def project_generic_generate_image_schema(source_schema: dict[str, Any]) -> dict[str, Any]:
    """为配置页投影与供应商无关的 generate/edit 条件参数 Schema。"""

    return _project_operation_branches(
        deepcopy(source_schema),
        ("generate", "edit"),
        supports_mask=True,
    )


def _set_enum(properties: dict[str, Any], field_name: str, values: tuple[str, ...]) -> None:
    """把稳定字符串能力写入对应参数枚举；空能力表示隐藏可选参数。"""

    field_schema = properties.get(field_name)
    if not isinstance(field_schema, dict):
        return
    if not values:
        properties.pop(field_name, None)
        return
    field_schema["enum"] = list(values)


def _remove_property(schema: dict[str, Any], field_name: str) -> None:
    """从模型可见 Schema 中删除参数及其 required 声明。"""

    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop(field_name, None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [item for item in required if item != field_name]


def _set_array_max_items(field_schema: Any, maximum: int) -> None:
    """兼容 nullable array 的 anyOf 结构并收窄数组上限。"""

    if not isinstance(field_schema, dict):
        return
    if field_schema.get("type") == "array":
        field_schema["maxItems"] = maximum
        return
    for variant in field_schema.get("anyOf", []):
        if isinstance(variant, dict) and variant.get("type") == "array":
            variant["maxItems"] = maximum


def _project_operation_branches(
    schema: dict[str, Any],
    operations: tuple[str, ...],
    *,
    supports_mask: bool,
) -> dict[str, Any]:
    """按 generate/edit 构造条件分支，直接表达参考图和蒙版约束。"""

    source_properties = schema.get("properties", {})
    source_required = list(schema.get("required", []))
    branches: list[dict[str, Any]] = []
    for operation in operations:
        if operation not in {"generate", "edit"}:
            continue
        properties = deepcopy(source_properties)
        properties["operation"] = {
            "type": "string",
            "const": operation,
            "description": source_properties.get("operation", {}).get("description", "图片操作类型。"),
        }
        required = list(source_required)
        if operation == "generate":
            properties.pop("mask_attachment_id", None)
        else:
            reference_schema = _required_array_schema(properties.get("reference_attachment_ids"))
            if reference_schema is not None:
                properties["reference_attachment_ids"] = reference_schema
            if "reference_attachment_ids" not in required:
                required.append("reference_attachment_ids")
            if not supports_mask:
                properties.pop("mask_attachment_id", None)
        branches.append(
            {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }
        )
    if not branches:
        return schema
    projected: dict[str, Any] = {
        "type": "object",
        "oneOf": branches,
    }
    if "$defs" in schema:
        projected["$defs"] = deepcopy(schema["$defs"])
    return projected


def _required_array_schema(field_schema: Any) -> dict[str, Any] | None:
    """从可空数组中提取数组分支，并保证编辑至少有一张参考图。"""

    if not isinstance(field_schema, dict):
        return None
    if field_schema.get("type") == "array":
        result = deepcopy(field_schema)
        result["minItems"] = max(1, int(result.get("minItems", 0)))
        return result
    for variant in field_schema.get("anyOf", []):
        if isinstance(variant, dict) and variant.get("type") == "array":
            result = deepcopy(variant)
            result["minItems"] = max(1, int(result.get("minItems", 0)))
            description = field_schema.get("description")
            if description:
                result["description"] = description
            return result
    return None
