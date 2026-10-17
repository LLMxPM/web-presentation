"""文件功能：验证自动放映配置 Schema、严格解析、组覆盖继承与 Runtime 映射的共享契约样例。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.slideshow import (
    build_runtime_advance,
    build_runtime_slideshow_defaults,
    build_runtime_transition,
    default_slideshow_payload,
    default_slideshow_settings,
    load_slideshow_settings,
    normalize_slideshow_settings,
    parse_route_advance_override,
    parse_route_transition_override,
    resolve_effective_slideshow,
)

_CASES_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "slideshow-contract-cases.json"


def _load_cases() -> dict[str, Any]:
    """读取跨模块共享的放映配置正反例。"""

    return json.loads(_CASES_PATH.read_text(encoding="utf-8"))


def _first_error_type(exc: ValidationError) -> str:
    """取首个校验错误类型，便于样例断言具体拒绝原因。"""

    return exc.errors()[0]["type"]


@pytest.mark.parametrize("case", _load_cases()["project_cases"], ids=lambda case: case["name"])
def test_project_slideshow_cases_should_match_shared_contract(case: dict[str, Any]) -> None:
    """项目完整配置按共享样例接受或拒绝。"""

    if case["valid"]:
        settings = normalize_slideshow_settings(case["input"])
        assert settings.model_dump(mode="json") == case["input"]
        return

    with pytest.raises(ValidationError) as excinfo:
        normalize_slideshow_settings(case["input"])
    assert _first_error_type(excinfo.value) == case["error"]


@pytest.mark.parametrize(
    ("group", "parser"),
    [
        ("route_transition_cases", parse_route_transition_override),
        ("route_advance_cases", parse_route_advance_override),
    ],
)
def test_route_override_cases_should_match_shared_contract(
    group: str,
    parser: Callable[[object | None], object],
) -> None:
    """路由覆盖按整组语义解析，null 表示继承。"""

    for case in _load_cases()[group]:
        if case["valid"]:
            parsed = parser(case["input"])
            if case["expected"] is None:
                assert parsed is None
            else:
                assert parsed is not None
                assert parsed.model_dump(mode="json") == case["expected"]  # type: ignore[attr-defined]
            continue

        with pytest.raises(ValidationError) as excinfo:
            parser(case["input"])
        assert _first_error_type(excinfo.value) == case["error"]


def test_defaults_should_match_shared_contract() -> None:
    """默认完整值与共享样例一致，且空值读取补默认值。"""

    cases = _load_cases()
    assert default_slideshow_payload() == cases["defaults"]["api"]
    assert load_slideshow_settings(None).model_dump(mode="json") == cases["defaults"]["api"]
    assert normalize_slideshow_settings(default_slideshow_payload()) == default_slideshow_settings()


@pytest.mark.parametrize("case", _load_cases()["resolution_cases"], ids=lambda case: case["name"])
def test_effective_slideshow_should_fallback_per_group(case: dict[str, Any]) -> None:
    """生效值按组独立回退，组内不做字段级继承。"""

    settings = normalize_slideshow_settings(case["slideshow"])
    effective = resolve_effective_slideshow(
        settings,
        parse_route_transition_override(case["transition"]),
        parse_route_advance_override(case["advance"]),
    )
    assert effective.to_api_dict() == case["expected"]


@pytest.mark.parametrize("case", _load_cases()["runtime_cases"], ids=lambda case: case["name"])
def test_runtime_mapping_should_use_camel_case(case: dict[str, Any]) -> None:
    """snake_case 项目值转换为 Runtime camelCase，叶子生效值独立下发。"""

    settings = normalize_slideshow_settings(case["slideshow"])
    assert build_runtime_slideshow_defaults(settings) == case["expected_defaults"]

    effective = resolve_effective_slideshow(
        settings,
        parse_route_transition_override(case["transition"]),
        parse_route_advance_override(case["advance"]),
    )
    assert {
        "transition": build_runtime_transition(effective.transition),
        "advance": build_runtime_advance(effective.advance),
    } == case["expected_route"]


@pytest.mark.parametrize("value", [None, [], "fade", 400, True])
def test_route_override_should_reject_non_object_values(value: object) -> None:
    """路由覆盖只接受完整对象或 null，其余类型明确拒绝。"""

    if value is None:
        assert parse_route_transition_override(value) is None
        assert parse_route_advance_override(value) is None
        return

    with pytest.raises(TypeError):
        parse_route_transition_override(value)
    with pytest.raises(TypeError):
        parse_route_advance_override(value)


def test_project_settings_should_reject_non_object_values() -> None:
    """项目配置不接受列表、字符串等非对象形态。"""

    for value in ([], "fade", 400, True):
        with pytest.raises(TypeError, match="完整 JSON 对象"):
            normalize_slideshow_settings(value)


def test_media_end_should_parse_and_map_after_capability_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """能力开放后 media_end 可按完整结构解析，并下发超时与停留时间。"""

    from app.schemas import slideshow as slideshow_module

    monkeypatch.setattr(
        slideshow_module,
        "SLIDESHOW_EXECUTABLE_ADVANCE_MODES",
        ("manual", "timer", "media_end"),
    )
    settings = normalize_slideshow_settings(
        {
            "transition": {"effect": "fade", "duration_ms": 400},
            "advance": {"mode": "media_end", "delay_ms": 6000, "media_timeout_ms": 120000},
            "loop": False,
            "auto_start": True,
        }
    )
    assert build_runtime_advance(settings.advance) == {
        "mode": "media_end",
        "delayMs": 6000,
        "mediaTimeoutMs": 120000,
    }
    with pytest.raises(ValidationError):
        normalize_slideshow_settings(
            {
                "transition": {"effect": "fade", "duration_ms": 400},
                "advance": {"mode": "media_end", "delay_ms": 6000, "media_timeout_ms": 999},
                "loop": False,
                "auto_start": False,
            }
        )
