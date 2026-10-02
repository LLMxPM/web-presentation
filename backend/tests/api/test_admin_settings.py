"""文件功能：验证系统设置管理接口权限、配置读取、批量热更新与时区公开端点同步。"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clean_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_admin_settings_permission_boundary(client: AsyncClient) -> None:
    """未登录用户访问系统设置接口应被 401 拦截。"""
    response = await client.get("/api/v1/admin/settings")
    assert response.status_code == 401


async def test_admin_settings_get_and_structure(authenticated_client: AsyncClient) -> None:
    """管理员获取系统设置列表，结构应包含 5 个分类且敏感信息已脱敏。"""
    response = await authenticated_client.get("/api/v1/admin/settings")
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "categories" in data
    assert "safe_mode_warnings" in data

    categories = {c["category"]: c for c in data["categories"]}
    expected_categories = {"storage", "general", "security", "ai", "diagnostic"}
    assert set(categories.keys()) == expected_categories

    # 验证全部 19 项配置都在 items 中
    items_map = {item["key"]: item for item in data["items"]}
    assert len(items_map) == 19
    assert items_map["app_timezone"]["value"] == "Asia/Shanghai"
    assert items_map["asset_storage_driver"]["value"] == "local"

    # 验证兼顾 /api/admin/settings 别名路径
    alias_resp = await authenticated_client.get("/api/admin/settings")
    assert alias_resp.status_code == 200


async def test_admin_settings_put_hot_reload_and_public_endpoint(authenticated_client: AsyncClient, client: AsyncClient) -> None:
    """测试管理员通过 PUT 更新设置后，进程内热更新生效，且公开端点同步返回最新时区。"""
    # 1. 验证公开端点初始时区
    init_pub = await client.get("/api/system/settings")
    assert init_pub.status_code == 200
    assert init_pub.json()["app_timezone"] == "Asia/Shanghai"

    # 2. 管理员更新业务时区与品牌名
    update_payload = {
        "settings": {
            "app_name": "全新的演示文稿平台",
            "app_timezone": "Asia/Tokyo",
            "session_ttl_hours": 48,
        }
    }
    update_resp = await authenticated_client.put("/api/v1/admin/settings", json=update_payload)
    assert update_resp.status_code == 200
    updated_data = update_resp.json()

    updated_map = {item["key"]: item for item in updated_data["items"]}
    assert updated_map["app_name"]["value"] == "全新的演示文稿平台"
    assert updated_map["app_timezone"]["value"] == "Asia/Tokyo"
    assert updated_map["session_ttl_hours"]["value"] == 48

    # 3. 验证进程内 get_settings() 已热生效
    active_settings = get_settings()
    assert active_settings.app_name == "全新的演示文稿平台"
    assert active_settings.app_timezone == "Asia/Tokyo"
    assert active_settings.session_ttl_hours == 48

    # 4. 验证公开端点 /api/system/settings 立即返回新时区
    after_pub = await client.get("/api/system/settings")
    assert after_pub.status_code == 200
    assert after_pub.json()["app_timezone"] == "Asia/Tokyo"


async def test_admin_settings_s3_test_connection_endpoint(authenticated_client: AsyncClient) -> None:
    """测试 S3 存储连通性测试接口。"""
    # 1. 缺少密钥时报错
    resp = await authenticated_client.post(
        "/api/v1/admin/settings/storage/test-connection",
        json={"bucket": "my-bucket"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "必须提供有效的 S3 Access Key" in data["message"]

    # 2. 模拟连通成功
    mock_client = AsyncMock()
    mock_client.head_bucket = AsyncMock(return_value={})
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_client

    with patch("aioboto3.Session", return_value=mock_session):
        success_resp = await authenticated_client.post(
            "/api/v1/admin/settings/storage/test-connection",
            json={
                "endpoint_url": "https://s3.example.com",
                "access_key": "test_ak",
                "secret_key": "test_sk",
                "bucket": "my-bucket",
            },
        )
        assert success_resp.status_code == 200
        res_data = success_resp.json()
        assert res_data["success"] is True
        assert "连通性测试成功" in res_data["message"]
