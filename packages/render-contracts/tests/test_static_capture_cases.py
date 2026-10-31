"""文件功能：使用 Runtime/Renderer 共享静态样本对拍 Python DTO 与两版 JSON Schema。"""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from render_contracts.errors import RenderContractError
from render_contracts.screenshot import ScreenshotPhaseResult

CASES = json.loads((Path(__file__).parents[3] / "tests/fixtures/static-capture-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_screenshot_phase_semantics_match_json_schema(case, version):
    """三类失败语义不能互换；每个样本同时经 Python 和 JSON Schema 边界。"""
    schema = json.loads((Path(__file__).parents[1] / f"schemas/execution-result.v{version}.json").read_text())
    validator = Draft202012Validator(schema["properties"]["screenshot"])
    if case.get("invalid"):
        with pytest.raises(RenderContractError):
            ScreenshotPhaseResult.from_dict(case["phase"])
        with pytest.raises(ValidationError):
            validator.validate(case["phase"])
    else:
        assert ScreenshotPhaseResult.from_dict(case["phase"]).to_dict() == case["phase"]
        validator.validate(case["phase"])
