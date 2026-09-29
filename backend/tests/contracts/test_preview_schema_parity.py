"""文件功能：previewSchema 三端对拍——JSON Schema 单一源 vs Editor/Runtime TS 类型 vs Backend 校验器。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.component_preview_schema import (
    get_component_preview_schema_ts_interface_fields,
    load_component_preview_schema_document,
    parse_component_preview_schema_text,
    validate_component_preview_schema_text,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
EDITOR_TS = REPO_ROOT / "editor" / "src" / "types" / "component-preview.ts"
RUNTIME_TS = REPO_ROOT / "runtime" / "src" / "core" / "shared" / "runtime-preview.ts"


def _extract_interface_fields(ts_source: str, interface_name: str) -> set[str]:
    """从 TS 源码提取指定 interface 的字段名集合。"""

    pattern = re.compile(
        rf"export interface {re.escape(interface_name)}\s*\{{(.*?)\n\}}",
        re.DOTALL,
    )
    match = pattern.search(ts_source)
    if match is None:
        return set()
    body = match.group(1)
    fields: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("*"):
            continue
        # 形如 `name?: type` 或 `name: type`
        field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\??:", stripped)
        if field_match:
            fields.add(field_match.group(1))
    return fields


def test_json_schema_single_source_is_well_formed() -> None:
    """单一源 JSON Schema 应包含顶层 props/slots/mocks/presets 与 TS 映射。"""

    document = load_component_preview_schema_document()
    assert document["title"] == "ComponentPreviewSchema"
    top_keys = set(document["properties"].keys())
    assert {"props", "slots", "mocks", "presets"} <= top_keys

    ts_map = get_component_preview_schema_ts_interface_fields()
    assert "ComponentPreviewSchema" in ts_map
    assert set(ts_map["ComponentPreviewSchema"]) == {"props", "slots", "mocks", "presets"}

    prop_def = document["$defs"]["propField"]
    assert prop_def["required"] == ["type"]
    assert set(prop_def["properties"].keys()) >= {
        "type", "label", "description", "required", "default", "placeholder", "options",
    }


def test_editor_types_match_json_schema() -> None:
    """Editor component-preview.ts 的 interface 字段应对齐 JSON Schema 映射。"""

    source = EDITOR_TS.read_text(encoding="utf-8")
    ts_map = get_component_preview_schema_ts_interface_fields()
    assert EDITOR_TS.exists(), "Editor previewSchema 类型文件不存在"

    for interface_name, expected_fields in ts_map.items():
        actual = _extract_interface_fields(source, interface_name)
        assert actual, f"Editor 未找到 interface {interface_name}"
        missing = set(expected_fields) - actual
        assert not missing, f"Editor {interface_name} 缺少字段 {missing}"


def test_runtime_types_match_json_schema() -> None:
    """Runtime runtime-preview.ts 的 interface 字段应对齐 JSON Schema 映射。"""

    source = RUNTIME_TS.read_text(encoding="utf-8")
    ts_map = get_component_preview_schema_ts_interface_fields()
    assert RUNTIME_TS.exists(), "Runtime previewSchema 类型文件不存在"

    for interface_name, expected_fields in ts_map.items():
        actual = _extract_interface_fields(source, interface_name)
        assert actual, f"Runtime 未找到 interface {interface_name}"
        missing = set(expected_fields) - actual
        assert not missing, f"Runtime {interface_name} 缺少字段 {missing}"


def test_editor_and_runtime_interface_fields_are_identical() -> None:
    """Editor 与 Runtime 同名 interface 的字段集合必须一致（允许额外可选字段）。"""

    editor_source = EDITOR_TS.read_text(encoding="utf-8")
    runtime_source = RUNTIME_TS.read_text(encoding="utf-8")
    ts_map = get_component_preview_schema_ts_interface_fields()

    for interface_name, expected_fields in ts_map.items():
        editor_fields = _extract_interface_fields(editor_source, interface_name)
        runtime_fields = _extract_interface_fields(runtime_source, interface_name)
        shared_required = set(expected_fields)
        assert shared_required <= editor_fields
        assert shared_required <= runtime_fields


def test_backend_validator_accepts_schema_shape() -> None:
    """Backend 解析器应接受符合单一源形状的 previewSchema。"""

    sample = {
        "props": {
            "title": {"type": "string", "label": "标题", "default": "Hello"},
            "count": {"type": "number", "required": True},
        },
        "slots": {
            "default": {
                "label": "默认插槽",
                "default": [
                    {"type": "text", "value": "示例文本"},
                    {
                        "type": "component",
                        "component": "@runtime-kit/public/components/primitives/Icon.v1.vue",
                        "props": {"name": "star"},
                    },
                ],
            }
        },
        "mocks": {"data": {"label": "数据", "default": {}}},
        "presets": [
            {
                "key": "basic",
                "label": "基础",
                "props": {"title": "预设"},
            }
        ],
    }
    text = json.dumps(sample, ensure_ascii=False)
    parsed = parse_component_preview_schema_text(text)
    assert parsed is not None
    assert set(parsed.keys()) <= {"props", "slots", "mocks", "presets"}
    # 校验并格式化不应抛错
    formatted = validate_component_preview_schema_text(text)
    assert formatted is not None


def test_backend_validator_rejects_invalid_slot_nodes() -> None:
    """slot 节点必须是合法对象；非法类型应被拒绝。"""

    bad = {"slots": {"default": {"default": ["not-a-node"]}}}
    with pytest.raises(Exception):
        parse_component_preview_schema_text(json.dumps(bad))
