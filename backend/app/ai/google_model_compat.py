"""文件功能：为 Google Gemini function response 提供 JSON Schema 引用兼容处理。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.genai.types import PartDict
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.google import GoogleModel

_LOCAL_SCHEMA_REF_PREFIX = "#/$defs/"


def inline_google_local_schema_refs(value: Any) -> Any:
    """递归展开工具返回中的本地 JSON Schema 引用，避免 Gemini 误判为多模态引用。"""

    return _inline_json_value(value, definitions={}, active_refs=frozenset())


def _inline_json_value(
    value: Any,
    *,
    definitions: Mapping[str, Any],
    active_refs: frozenset[str],
) -> Any:
    """展开单个 JSON 值，并保留无法安全解析的外部或循环引用。"""

    if isinstance(value, list):
        return [
            _inline_json_value(item, definitions=definitions, active_refs=active_refs)
            for item in value
        ]
    if not isinstance(value, Mapping):
        return value

    raw_definitions = value.get("$defs")
    scoped_definitions = definitions
    if isinstance(raw_definitions, Mapping):
        scoped_definitions = {
            **definitions,
            **{str(name): definition for name, definition in raw_definitions.items()},
        }
    should_remove_definitions = isinstance(raw_definitions, Mapping) and _contains_local_schema_ref(value)

    ref = value.get("$ref")
    if isinstance(ref, str) and ref.startswith(_LOCAL_SCHEMA_REF_PREFIX):
        definition_name = ref[len(_LOCAL_SCHEMA_REF_PREFIX):]
        definition = scoped_definitions.get(definition_name)
        if definition is not None and ref not in active_refs:
            expanded = _inline_json_value(
                definition,
                definitions=scoped_definitions,
                active_refs=active_refs | {ref},
            )
            siblings = {
                key: item
                for key, item in value.items()
                if key != "$ref"
            }
            if not siblings:
                return expanded
            if isinstance(expanded, Mapping):
                return {
                    **expanded,
                    **{
                        key: _inline_json_value(
                            item,
                            definitions=scoped_definitions,
                            active_refs=active_refs,
                        )
                        for key, item in siblings.items()
                    },
                }

    result: dict[str, Any] = {}
    for key, item in value.items():
        if key == "$defs" and should_remove_definitions:
            continue
        if key == "mapping" and scoped_definitions and isinstance(item, Mapping):
            item = {
                mapping_key: mapping_value
                for mapping_key, mapping_value in item.items()
                if not _is_local_schema_ref(mapping_value)
            }
        result[key] = _inline_json_value(item, definitions=scoped_definitions, active_refs=active_refs)
    return result


def _is_local_schema_ref(value: Any) -> bool:
    """判断字符串是否为 Gemini 会误解的本地 JSON Schema 引用。"""

    return isinstance(value, str) and value.startswith(_LOCAL_SCHEMA_REF_PREFIX)


def _contains_local_schema_ref(value: Any) -> bool:
    """递归判断值中是否存在 Gemini 会误解的本地 Schema 引用。"""

    if isinstance(value, list):
        return any(_contains_local_schema_ref(item) for item in value)
    if not isinstance(value, Mapping):
        return False
    if _is_local_schema_ref(value.get("$ref")):
        return True
    discriminator_mapping = value.get("mapping")
    if isinstance(discriminator_mapping, Mapping) and any(
        _is_local_schema_ref(item) for item in discriminator_mapping.values()
    ):
        return True
    return any(_contains_local_schema_ref(item) for item in value.values())


class GoogleCompatibleModel(GoogleModel):
    """兼容 Gemini function response 对本地 JSON Schema `$ref` 的错误解释。"""

    async def _map_tool_return(self, part: ToolReturnPart) -> list[PartDict]:
        """映射工具返回，并仅清理 Google function response 中的本地 Schema 引用。"""

        mapped_parts = await super()._map_tool_return(part)
        for mapped_part in mapped_parts:
            function_response = mapped_part.get("function_response")
            if not isinstance(function_response, dict):
                continue
            response = function_response.get("response")
            if response is None:
                continue
            function_response["response"] = inline_google_local_schema_refs(response)
        return mapped_parts
