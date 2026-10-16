"""文件功能：校验 ModelViewOptions 共享正反例在 Backend 侧得到与契约一致的结论。"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.model_view_options import validate_model_view_options

_CASES_PATH = Path(__file__).resolve().parents[2] / "app" / "core" / "model_view_options.v1.cases.json"
_CASES = json.loads(_CASES_PATH.read_text(encoding="utf-8"))


def test_shared_valid_cases_pass_backend_validation() -> None:
    """共享正例必须全部通过 Backend 校验。"""

    for case in _CASES["valid"]:
        errors = validate_model_view_options(case)
        assert errors == [], f"应通过却失败：{case} -> {errors}"


def test_shared_invalid_cases_rejected_by_backend_validation() -> None:
    """共享反例必须全部被 Backend 校验拒绝，并给出有界错误。"""

    for case in _CASES["invalid"]:
        errors = validate_model_view_options(case["value"])
        assert errors, f"应拒绝却通过：{case['reason']} -> {case['value']}"
        assert all(isinstance(item, str) and len(item) <= 120 for item in errors)


def test_non_finite_numbers_rejected() -> None:
    """非有限数值不能出现在相机参数与视场角中。"""

    assert validate_model_view_options(
        {"name": "p", "cameraPosition": [0, float("nan"), 4], "cameraTarget": [0, 0, 0]}
    )
    assert validate_model_view_options({"name": "p", "cameraFov": float("inf")})


def test_unknown_keys_are_ignored_for_host_attrs() -> None:
    """未声明的透传字段（如 style）不参与校验，保持宿主 attrs 兼容。"""

    errors = validate_model_view_options({"name": "p", "style": "width: 100%"})
    assert errors == []


def test_payload_must_be_object() -> None:
    """展示参数必须是 JSON 对象。"""

    assert validate_model_view_options("product")
    assert validate_model_view_options(None)
