"""文件功能：验证历史数据库时间经真实 API 返回 UTC，以及前端公开业务时区配置。"""

from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory


async def test_workspace_api_should_add_utc_to_legacy_timestamps(authenticated_client: AsyncClient) -> None:
    """历史 SQLite 时间在详情和列表响应中直接补 UTC，不依赖客户端时区。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": "历史时间空间", "status": "active"})
    assert response.status_code == 200
    workspace_id = response.json()["id"]
    assert response.json()["created_at"].endswith("Z")
    async with get_session_factory()() as session:
        await session.execute(text(
            "UPDATE workspaces SET created_at = '2026-09-21 02:00:00', "
            "updated_at = '2026-09-21 03:00:00' WHERE id = :id"
        ), {"id": workspace_id})
        await session.commit()
    response = await authenticated_client.get(f"/api/workspaces/{workspace_id}")
    assert response.status_code == 200
    assert response.json()["created_at"] == "2026-09-21T02:00:00Z"
    assert response.json()["updated_at"] == "2026-09-21T03:00:00Z"
    response = await authenticated_client.get("/api/workspaces")
    assert response.status_code == 200
    item = next(item for item in response.json()["items"] if item["id"] == workspace_id)
    assert item["updated_at"] == "2026-09-21T03:00:00Z"


async def test_system_settings_should_publish_only_app_timezone(client: AsyncClient, monkeypatch) -> None:
    """启动配置无需登录，只返回部署业务时区，不暴露其它服务端设置。"""

    monkeypatch.setenv("APP_TIMEZONE", "Asia/Tokyo")
    get_settings.cache_clear()
    try:
        response = await client.get("/api/system/settings")
        assert response.status_code == 200
        assert response.json() == {"app_timezone": "Asia/Tokyo"}
    finally:
        get_settings.cache_clear()
