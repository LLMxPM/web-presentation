"""文件功能：使用三端共享正反例验证 previewSchema 生产结构校验与引用权限边界。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.component_preview_schema import (
    parse_component_preview_schema_text,
    validate_component_preview_schema_text,
)
from app.core.exceptions import AppException

CASES = json.loads(
    (
        Path(__file__).resolve().parents[3] / "tests/fixtures/preview-schema-cases.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize("sample", CASES, ids=[sample["name"] for sample in CASES])
def test_production_validator_shared_cases(sample: dict) -> None:
    """合法样本往返不丢字段；非法字段类型、必填、枚举和嵌套形状被生产入口拒绝。"""
    text = json.dumps(sample["value"], ensure_ascii=False)
    if sample["valid"]:
        assert parse_component_preview_schema_text(text) == sample["value"]
        assert (
            json.loads(validate_component_preview_schema_text(text)) == sample["value"]
        )
    else:
        with pytest.raises(AppException) as error:
            parse_component_preview_schema_text(text)
        assert error.value.code == "COMPONENT_PREVIEW_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "module",
    ["vue", "./private.vue", "@runtime-kit/public/components/primitives/Icon.vue"],
)
def test_structure_validation_preserves_import_boundary(module: str) -> None:
    """结构合法不等于引用获准；插槽和预设仍受版本化 import 规则约束。"""
    node = {"type": "component", "component": module}
    for sample in [
        {"slots": {"default": {"default": [node]}}},
        {"presets": [{"key": "a", "label": "A", "slots": {"default": [node]}}]},
    ]:
        with pytest.raises(AppException) as error:
            parse_component_preview_schema_text(json.dumps(sample))
        assert error.value.code == "COMPONENT_PREVIEW_SCHEMA_INVALID"
