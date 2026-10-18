"""文件功能：验证音频共享契约的严格解析、默认值、能力阶段与 Runtime 映射。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.schemas.audio import (
    AUDIO_ALLOWED_CONTENT_TYPES_BY_EXTENSION,
    AUDIO_MILESTONE_CAPABILITIES,
    AUDIO_SCHEMA_VERSION,
    AssetAudioPropsContract,
    AudioCueBindingInput,
    AudioVolumeSettings,
    ResolvedAudioCueBinding,
    build_runtime_audio_config,
    default_audio_volume_payload,
    default_project_audio_settings,
    load_audio_volume_settings,
    normalize_project_audio_settings,
)
from pydantic import ValidationError

_CASES_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "audio-contract-cases.json"


def _load_cases() -> dict[str, Any]:
    """读取 Backend 与根仓契约测试共用的音频正反例。"""

    return json.loads(_CASES_PATH.read_text(encoding="utf-8"))


def _first_error_type(exc: ValidationError) -> str:
    """提取第一个 Pydantic 错误类型，锁定拒绝语义。"""

    return exc.errors()[0]["type"]


def test_resource_and_capability_constants_should_match_fixture() -> None:
    """资源格式与里程碑能力名称只由音频 Schema 和共享 fixture 维护。"""

    cases = _load_cases()
    assert AUDIO_SCHEMA_VERSION == cases["schema_version"]
    assert {key: list(value) for key, value in AUDIO_ALLOWED_CONTENT_TYPES_BY_EXTENSION.items()} == cases["resource"][
        "extensions"
    ]
    assert {key: list(value) for key, value in AUDIO_MILESTONE_CAPABILITIES.items()} == cases["capabilities"]


def test_defaults_should_match_fixture_and_historical_null() -> None:
    """历史空值读取为默认三段音量且没有任何 cue。"""

    expected = _load_cases()["defaults"]["api"]
    settings = default_project_audio_settings()
    assert settings.model_dump(mode="json") == expected
    assert default_audio_volume_payload() == {key: expected[key] for key in default_audio_volume_payload()}
    assert load_audio_volume_settings(None) == settings.volume_settings()


@pytest.mark.parametrize("case", _load_cases()["settings_cases"], ids=lambda case: case["name"])
def test_project_settings_should_match_shared_cases(case: dict[str, Any]) -> None:
    """项目完整音频设置按共享正反例接受或拒绝。"""

    if case["valid"]:
        assert normalize_project_audio_settings(case["input"]).model_dump(mode="json") == case["input"]
        return
    with pytest.raises(ValidationError) as excinfo:
        normalize_project_audio_settings(case["input"])
    assert _first_error_type(excinfo.value) == case["error"]


@pytest.mark.parametrize("case", _load_cases()["cue_cases"], ids=lambda case: case["name"])
def test_cue_binding_should_match_shared_cases(case: dict[str, Any]) -> None:
    """cue key、资产 ID 与增益使用严格类型和命名空间约束。"""

    if case["valid"]:
        assert AudioCueBindingInput.model_validate(case["input"]).model_dump(mode="json") == case["input"]
        return
    with pytest.raises(ValidationError) as excinfo:
        AudioCueBindingInput.model_validate(case["input"])
    assert _first_error_type(excinfo.value) == case["error"]


@pytest.mark.parametrize("case", _load_cases()["asset_audio_cases"], ids=lambda case: case["name"])
def test_asset_audio_props_should_match_shared_cases(case: dict[str, Any]) -> None:
    """AssetAudio 公开属性拒绝 autoplay、循环旁白和宽松数字。"""

    if case["valid"]:
        parsed = AssetAudioPropsContract.model_validate(case["input"])
        assert parsed.resolved_controls() is case["expected_controls"]
        return
    with pytest.raises(ValidationError) as excinfo:
        AssetAudioPropsContract.model_validate(case["input"])
    assert _first_error_type(excinfo.value) == case["error"]


@pytest.mark.parametrize("case", _load_cases()["runtime_cases"], ids=lambda case: case["name"])
def test_runtime_mapping_should_match_shared_cases(case: dict[str, Any]) -> None:
    """Backend 快照映射使用 camelCase、0–1 增益和确定性 cue 顺序。"""

    volume = AudioVolumeSettings.model_validate(case["volume"])
    cues = [ResolvedAudioCueBinding.model_validate(value) for value in case["cues"]]
    assert build_runtime_audio_config(volume, cues) == case["expected"]


@pytest.mark.parametrize("value", [[], "audio", 100, True])
def test_non_object_settings_should_be_rejected(value: object) -> None:
    """项目音频设置不接受对象之外的宽松形态。"""

    with pytest.raises(TypeError, match="完整 JSON 对象"):
        normalize_project_audio_settings(value)
