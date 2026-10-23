"""文件功能：验证页内编排能力端点默认开放及独立截图能力状态。"""

from httpx import AsyncClient

from app.schemas.timeline import (
    TIMELINE_CAPABILITY_ENABLED,
    TIMELINE_CAPTURE_SNAPSHOT_ENABLED,
    TIMELINE_EXECUTABLE_ADVANCE_MODES,
    TIMELINE_SCHEMA_VERSION,
    TIMELINE_TRACK_TYPES,
)


async def test_system_timeline_capabilities_publish_enabled_playback(client: AsyncClient) -> None:
    """时间轴与结束推进默认开放，指定时刻截图仍保持独立关闭。"""

    response = await client.get("/api/system/timeline-capabilities")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == TIMELINE_SCHEMA_VERSION
    assert data["enabled"] is TIMELINE_CAPABILITY_ENABLED
    assert data["capture_snapshot"] is TIMELINE_CAPTURE_SNAPSHOT_ENABLED
    assert data["advance_modes"] == list(TIMELINE_EXECUTABLE_ADVANCE_MODES)
    assert data["enabled"] is True
    assert data["track_types"] == list(TIMELINE_TRACK_TYPES)
    assert data["advance_modes"] == ["timeline_end"]
    assert data["capture_snapshot"] is False
