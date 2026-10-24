"""文件功能：验证音频能力静态判定、别名导入识别与检查指纹能力身份。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import config as app_config
from app.schemas import audio as audio_schema
from app.services.audio_options_gate import collect_audio_capability_errors
from app.services.code_check_fingerprint import audio_capability_identity

ALL_CAPABILITIES = frozenset(
    {
        audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS,
        audio_schema.AUDIO_CAPABILITY_PAGE_NARRATION,
        audio_schema.AUDIO_CAPABILITY_AUDIO_CUES,
    }
)


def _use_capabilities(monkeypatch: pytest.MonkeyPatch, capabilities: frozenset[str]) -> None:
    """替换当前开放能力集合，模拟不同阶段出口组合。"""

    monkeypatch.setattr(audio_schema, "AUDIO_OPEN_CAPABILITIES", capabilities)


def test_dev_switch_only_expands_audio_capabilities_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """联合验收开关默认不改变发布集合，显式开启才纳入旁白和 cue。"""

    monkeypatch.setattr(
        app_config,
        "get_settings",
        lambda: SimpleNamespace(audio_dev_capabilities_enabled=False),
    )
    assert audio_schema.get_open_audio_capabilities() == frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS})

    monkeypatch.setattr(
        app_config,
        "get_settings",
        lambda: SimpleNamespace(audio_dev_capabilities_enabled=True),
    )
    assert audio_schema.get_open_audio_capabilities() == ALL_CAPABILITIES


def test_content_audio_is_not_blocked_by_closed_narration_or_cues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """内容音频只依赖 audio_assets，不应被旁白或 cue 开关误伤。"""

    _use_capabilities(monkeypatch, frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS}))

    assert collect_audio_capability_errors('<template><AssetAudio name="bgm" /></template>') == []


def test_narration_is_rejected_when_page_narration_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """静态 purpose=narration 在能力关闭时给出稳定能力提示。"""

    _use_capabilities(monkeypatch, frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS}))

    errors = collect_audio_capability_errors(
        '<template><AssetAudio name="bgm" purpose="narration" /></template>'
    )

    assert len(errors) == 1
    assert "page_narration" in errors[0]


def test_use_audio_cue_alias_is_detected_when_cues_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """命名别名导入与调用必须被识别，不能只匹配原始函数名。"""

    _use_capabilities(monkeypatch, frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS}))
    source = (
        "<script setup lang=\"ts\">\n"
        "import { useAudioCue as playCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'\n"
        "const { playCue: play } = playCue()\n"
        "</script>\n"
    )

    errors = collect_audio_capability_errors(source)

    assert len(errors) == 1
    assert "audio_cues" in errors[0]


def test_open_capabilities_allow_narration_and_cue(monkeypatch: pytest.MonkeyPatch) -> None:
    """能力全部开放时相同源码不再产生能力错误。"""

    _use_capabilities(monkeypatch, ALL_CAPABILITIES)
    source = (
        "<template><AssetAudio name=\"bgm\" purpose=\"narration\" /></template>\n"
        "<script setup lang=\"ts\">\n"
        "import { useAudioCue } from '@runtime-kit/public/composables/audio/useAudioCue.v1'\n"
        "useAudioCue()\n"
        "</script>\n"
    )

    assert collect_audio_capability_errors(source) == []


def test_code_check_identity_tracks_capability_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """能力集合变化必须改变检查指纹输入，避免复用关闭期间的 valid 缓存。"""

    _use_capabilities(monkeypatch, frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS}))
    closed_identity = audio_capability_identity()
    _use_capabilities(monkeypatch, ALL_CAPABILITIES)

    assert closed_identity == ["audio_assets"]
    assert audio_capability_identity() == ["audio_assets", "audio_cues", "page_narration"]


def test_validate_failure_uses_same_business_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate 与同步写入必须返回同一能力业务码，避免客户端出现第二套错误语义。"""

    from app.services.code_check_service import CodeCheckService

    _use_capabilities(monkeypatch, frozenset({audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS}))
    failure = CodeCheckService._audio_option_failure(
        '<template><AssetAudio name="bgm" purpose="narration" /></template>'
    )

    assert failure is not None
    assert failure["success"] is False
    assert failure["status"] == "failed"
    diagnostics = failure["diagnostics"]
    assert diagnostics[0]["code"] == "AUDIO_CAPABILITY_UNAVAILABLE"
