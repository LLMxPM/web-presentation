"""文件功能：对拍独立静态截图契约，确保已移除选择器与采样回执在各版本均被拒绝。"""
import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from render_contracts.constants import PROTOCOL_VERSION, PROTOCOL_VERSION_V2
from render_contracts.errors import RenderContractError
from render_contracts.schema import ExecutionRequest, ExecutionResult
from test_schema_roundtrip import _request, _result


@pytest.mark.parametrize("version,protocol", [(1, PROTOCOL_VERSION), (2, PROTOCOL_VERSION_V2)])
@pytest.mark.parametrize("selection", [None, {}, {"timeline_id": "intro", "at_ms": 300}])
def test_removed_selector_is_rejected_in_all_protocols(version, protocol, selection):
    """字段即使为 null 也不能静默忽略；顶层与 operation_options 同时封口。"""
    request = replace(_request(), contract_version=protocol)
    schema = json.loads((Path(__file__).parents[1] / f"schemas/execution-request.v{version}.json").read_text())
    validator = Draft202012Validator(schema)
    payload = request.to_dict()
    validator.validate(payload)
    assert ExecutionRequest.from_dict(payload).to_dict() == payload
    for candidate in ({**payload, "motion_snapshot": selection},
                      {**payload, "operation_options": {"motion_snapshot": selection}}):
        with pytest.raises(ValidationError):
            validator.validate(candidate)
        with pytest.raises(RenderContractError, match="不再支持"):
            ExecutionRequest.from_dict(candidate).validate()


@pytest.mark.parametrize("version", [1, 2])
def test_static_result_has_no_applied_motion(version):
    """静态 PNG 不披露播放状态证明；旧回执不能继续作为有效结果传递。"""
    payload = _result().to_dict()
    schema = json.loads((Path(__file__).parents[1] / f"schemas/execution-result.v{version}.json").read_text())
    validator = Draft202012Validator(schema)
    validator.validate(payload)
    assert "applied_motion" not in payload
    for value in (None, {"status": "applied", "sampled_time_ms": 300}):
        candidate = {**payload, "applied_motion": value}
        with pytest.raises(ValidationError):
            validator.validate(candidate)
        with pytest.raises(RenderContractError, match="不再支持"):
            ExecutionResult.from_dict(candidate)
