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

    return schema


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
