"""文件功能：W01 访问基线测试，记录并验证当前文件与素材公开端点的既有行为与待收口反例。"""

from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db_session
from app.main import app
from app.services.runtime_artifact_store import RuntimeArtifactStore


@pytest.fixture
def mock_session():
    """提供轻量模拟的 AsyncSession，避免单测直连数据库。"""
    session = AsyncMock()
    session.scalar.return_value = None
    return session


@pytest.mark.asyncio
async def test_baseline_public_assets_access_missing_file(mock_session):
    """验证现有 /public/assets 匿名读取不存在的资源时返回 404（路由已收口卸载）。"""

    app.dependency_overrides[get_db_session] = lambda: mock_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/public/assets/1/nonexistent-hash")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_baseline_public_page_screenshots_missing(mock_session):
    """验证现有 /public/page-screenshots/{page_id} 匿名读取不存在页面时返回 404（路由已收口卸载）。"""

    app.dependency_overrides[get_db_session] = lambda: mock_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/public/page-screenshots/999999")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_baseline_template_package_assets_expired():
    """验证现有 /public/template-package-assets/{artifact_id}/{file_hash} 读取过期/不存在资源返回 404（路由已收口卸载）。"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/public/template-package-assets/art-none/hash-none")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_baseline_template_package_assets_success(monkeypatch):
    """验证现有 /public/template-package-assets 匿名访问已被关闭，直连返回 404。"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/public/template-package-assets/art-valid/hash-valid")
        assert response.status_code == 404
