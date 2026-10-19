"""文件功能：验证布局与截图阶段联合结果的增量兼容及 JSON Schema 往返。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from render_contracts.errors import RenderContractError
from render_contracts.schema import ExecutionResult
from render_contracts.screenshot import ScreenshotPhaseResult
from test_schema_roundtrip import _result


@pytest.mark.parametrize("status,reason", [("available", None), ("failed", "PNG_FAILED"), ("skipped", "NOT_REQUESTED")])
def test_joint_result_roundtrip(status, reason):
    """布局已完成时可独立表达截图成功、失败或跳过，旧消费者可忽略新字段。"""
    result = replace(_result(), operation="page.diagnose", screenshot=ScreenshotPhaseResult(status, reason))
    payload = result.to_dict()
    schema = json.loads((Path(__file__).parents[1] / "schemas/execution-result.v1.json").read_text())
    Draft202012Validator(schema).validate(payload)
    assert ExecutionResult.from_dict(payload).to_dict() == payload
    assert payload["layout"] and payload["artifacts"]
    payload.pop("screenshot")
    assert ExecutionResult.from_dict(payload).screenshot is None


def test_invalid_screenshot_phase_rejected():
    """图片缺失必须保留原因，不把错误重试字符串当真值。"""
    with pytest.raises(RenderContractError):
        ScreenshotPhaseResult("failed")
    with pytest.raises(RenderContractError):
        ScreenshotPhaseResult("available", retryable="false")
