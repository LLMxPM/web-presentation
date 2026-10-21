"""文件功能：验证页内编排能力端点默认关闭且字段与运行时常量一致。"""

from httpx import AsyncClient

from app.schemas.timeline import (
    TIMELINE_CAPABILITY_ENABLED,
    TIMELINE_CAPTURE_SNAPSHOT_ENABLED,
    TIMELINE_EXECUTABLE_ADVANCE_MODES,
    TIMELINE_SCHEMA_VERSION,
    TIMELINE_TRACK_TYPES,
)


async def test_system_timeline_capabilities_are_closed_before_g2(client: AsyncClient) -> None:
    """G2 前能力关闭，不通过 track_types 或推进模式暗示可执行。"""

    response = await client.get("/api/system/timeline-capabilities")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == TIMELINE_SCHEMA_VERSION
    assert data["enabled"] is TIMELINE_CAPABILITY_ENABLED
    assert data["capture_snapshot"] is TIMELINE_CAPTURE_SNAPSHOT_ENABLED
    assert data["advance_modes"] == list(TIMELINE_EXECUTABLE_ADVANCE_MODES)
    if not TIMELINE_CAPABILITY_ENABLED:
        assert data["track_types"] == []
        assert "timeline_end" not in data["advance_modes"]
    else:
        assert data["track_types"] == list(TIMELINE_TRACK_TYPES)
