"""文件功能：验证公开放映能力端点与当前写入门禁、范围常量保持一致。"""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.schemas import audio as audio_schema
from app.schemas.audio import AUDIO_SCHEMA_VERSION
from app.schemas.slideshow import (
    ADVANCE_DELAY_MAX_MS,
    ADVANCE_DELAY_MIN_MS,
    MEDIA_TIMEOUT_MAX_MS,
    MEDIA_TIMEOUT_MIN_MS,
    SLIDESHOW_EXECUTABLE_ADVANCE_MODES,
    SLIDESHOW_SCHEMA_VERSION,
    SLIDESHOW_TRANSITION_EFFECTS,
    TIMELINE_TIMEOUT_MAX_MS,
    TIMELINE_TIMEOUT_MIN_MS,
    TRANSITION_DURATION_MAX_MS,
    TRANSITION_DURATION_MIN_MS,
)
from app.services.audio_capability_gate import is_audio_capability_open


async def test_system_slideshow_capabilities_should_publish_executable_baseline(client: AsyncClient) -> None:
    """Editor 读取的能力声明与后端可写模式、范围一致，已验收媒体与演讲者能力开放。"""

    response = await client.get("/api/system/slideshow-capabilities")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SLIDESHOW_SCHEMA_VERSION
    assert data["transition_effects"] == list(SLIDESHOW_TRANSITION_EFFECTS)
    assert data["advance_modes"] == list(SLIDESHOW_EXECUTABLE_ADVANCE_MODES)
    assert "media_end" in data["advance_modes"]
    assert data["single_window_auto_play"] is True
    assert data["presenter_auto_play"] is True
    assert data["capture_auto_play"] is False
    assert data["transition_duration_ms"] == {
        "min": TRANSITION_DURATION_MIN_MS,
        "max": TRANSITION_DURATION_MAX_MS,
        "none": 0,
    }
    assert data["delay_ms"] == {"min": ADVANCE_DELAY_MIN_MS, "max": ADVANCE_DELAY_MAX_MS}
    assert data["media_timeout_ms"] == {"min": MEDIA_TIMEOUT_MIN_MS, "max": MEDIA_TIMEOUT_MAX_MS}
    assert data["timeline_timeout_ms"] == {"min": TIMELINE_TIMEOUT_MIN_MS, "max": TIMELINE_TIMEOUT_MAX_MS}
    assert "timeline_end" in data["advance_modes"]
    assert data["audio"] == {
        "schema_version": AUDIO_SCHEMA_VERSION,
        "audio_assets": True,
        "page_narration": False,
        "audio_cues": False,
    }


async def test_development_audio_capabilities_are_published(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本地联调显式开关应同时开放旁白与 cue 的公开能力声明。"""

    monkeypatch.setenv("AUDIO_DEV_CAPABILITIES_ENABLED", "true")
    get_settings.cache_clear()
    try:
        response = await client.get("/api/system/slideshow-capabilities")
        assert response.status_code == 200
        assert response.json()["audio"] == {
            "schema_version": AUDIO_SCHEMA_VERSION,
            "audio_assets": True,
            "page_narration": True,
            "audio_cues": True,
        }
    finally:
        get_settings.cache_clear()


async def test_audio_capability_disclosure_matches_enabled_write_gate(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """联合验收开放音频时，公共声明和写入门禁使用同一能力集合。"""

    monkeypatch.setattr(
        audio_schema,
        "get_open_audio_capabilities",
        lambda: frozenset(audio_schema.AUDIO_MILESTONE_CAPABILITIES["m2"]),
    )
    response = await client.get("/api/system/slideshow-capabilities")

    assert response.status_code == 200
    assert response.json()["audio"] == {
        "schema_version": AUDIO_SCHEMA_VERSION,
        "audio_assets": True,
        "page_narration": True,
        "audio_cues": True,
    }
    assert is_audio_capability_open(audio_schema.AUDIO_CAPABILITY_AUDIO_CUES)
