"""文件功能：验证公开放映能力端点与当前写入门禁、范围常量保持一致。"""

from httpx import AsyncClient

from app.schemas.slideshow import (
    ADVANCE_DELAY_MAX_MS,
    ADVANCE_DELAY_MIN_MS,
    MEDIA_TIMEOUT_MAX_MS,
    MEDIA_TIMEOUT_MIN_MS,
    SLIDESHOW_EXECUTABLE_ADVANCE_MODES,
    SLIDESHOW_SCHEMA_VERSION,
    SLIDESHOW_TRANSITION_EFFECTS,
    TRANSITION_DURATION_MAX_MS,
    TRANSITION_DURATION_MIN_MS,
)


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
