"""文件功能：统一解析 Pydantic AI 工具参数，保证运行态落库使用对象结构。"""

from __future__ import annotations

import json
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BeforeValidator

MAX_JSON_CONTAINER_DECODE_LAYERS = 4


def decode_json_container(
    value: Any,
    *,
    expected_types: tuple[type[dict] | type[list], ...],
    max_layers: int = MAX_JSON_CONTAINER_DECODE_LAYERS,
) -> Any:
    """按期望容器类型解开重复 JSON 序列化，且不转换容器内部的业务字符串。"""

    if isinstance(value, expected_types):
        return value
    current = value
    for _ in range(max(0, max_layers)):
        if not isinstance(current, str):
            return current
        stripped = current.strip()
        if not stripped or stripped[0] not in {'{', '[', '"'}:
            return current
        try:
            current = json.loads(stripped)
        except (TypeError, ValueError):
            return value
        if isinstance(current, expected_types):
            return current
    return current


def json_compatible_annotation(annotation: Any) -> Any:
    """为对象和数组参数增加前置兼容解析，同时保持原始 JSON Schema 类型。"""

    expected_types = _json_container_types(annotation)
    if not expected_types:
        return annotation

    def decode(value: Any) -> Any:
        """只解开参数根节点的重复 JSON 编码，不递归改写内部文本字段。"""

        return decode_json_container(value, expected_types=expected_types)

    return Annotated[annotation, BeforeValidator(decode)]


def _json_container_types(annotation: Any) -> tuple[type[dict] | type[list], ...]:
    """提取注解允许的 JSON 根容器类型，Optional/Annotated 会递归展开。"""

    origin = get_origin(annotation)
    if origin is Annotated:
        return _json_container_types(get_args(annotation)[0])
    if origin is dict or annotation is dict:
        return (dict,)
    if origin in {list, tuple, set} or annotation in {list, tuple, set}:
        return (list,)
    if origin in {Union, UnionType}:
        kinds = {
            kind
            for item in get_args(annotation)
            for kind in _json_container_types(item)
        }
        return tuple(kind for kind in (dict, list) if kind in kinds)
    return ()


def parse_tool_arguments(value: Any) -> dict[str, Any] | None:
    """将字典或多层 JSON 对象字符串解析为工具参数；非对象结构返回 None。"""

    parsed = decode_json_container(value, expected_types=(dict,))
    return dict(parsed) if isinstance(parsed, dict) else None
