"""文件功能：验证 Scene 自省只披露实际任务词汇、独立静态呈现与明确的开发执行上限。"""
from httpx import AsyncClient


async def test_scene_capabilities_and_removed_timeline_endpoint(client: AsyncClient) -> None:
    """新端点不保留旧时间轴能力或降级协商。"""
    response = await client.get("/api/system/scene-capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 1
    assert data["task_roles"] == ["blocking", "ambient"]
    assert data["advance_modes"] == ["manual", "timer", "scene_end"]
    assert data["static_presentation"] == "independent"
    assert data["max_tasks"] == 128
    assert "track_types" not in data
    assert (await client.get("/api/system/timeline-capabilities")).status_code == 404
