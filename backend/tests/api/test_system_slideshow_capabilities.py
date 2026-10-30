"""文件功能：验证放映 schema 4 的模式、边界与音频默认支持，不把能力布尔值当成实机验收。"""
from httpx import AsyncClient
from app.schemas.slideshow import SLIDESHOW_SCHEMA_VERSION


async def test_system_slideshow_capabilities_should_publish_scene_contract(client: AsyncClient) -> None:
    """完成后停留允许零，旧模式、旧预算与会话自动开始均不披露。"""
    response = await client.get("/api/system/slideshow-capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SLIDESHOW_SCHEMA_VERSION == 4
    assert data["advance_modes"] == ["manual", "timer", "scene_end"]
    assert data["transition_effects"] == ["none", "fade", "push"]
    assert data["delay_ms"] == {"min": 1000, "max": 3600000}
    assert data["completion_delay_ms"] == {"min": 0, "max": 3600000}
    assert data["capture_auto_play"] is False
    assert "media_timeout_ms" not in data and "timeline_timeout_ms" not in data
    assert data["audio"] == {"schema_version": 1, "audio_assets": True, "page_narration": True, "audio_cues": True}
