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
    """验证现有 /public/assets 匿名读取不存在的资源时返回 404。"""

    app.dependency_overrides[get_db_session] = lambda: mock_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/public/assets/1/nonexistent-hash")
            assert response.status_code == 404
            assert response.json().get("code") == "ASSET_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_baseline_public_page_screenshots_missing(mock_session):
    """验证现有 /public/page-screenshots/{page_id} 匿名读取不存在页面时返回 404。"""

    app.dependency_overrides[get_db_session] = lambda: mock_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/public/page-screenshots/999999")
            assert response.status_code == 404
            assert response.json().get("code") == "PAGE_SCREENSHOT_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_baseline_template_package_assets_expired():
    """验证现有 /public/template-package-assets/{artifact_id}/{file_hash} 读取过期/不存在资源返回 404。"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/public/template-package-assets/art-none/hash-none")
        assert response.status_code == 404
        assert response.json().get("code") == "TEMPLATE_PACKAGE_ASSET_NOT_FOUND"


@pytest.mark.asyncio
async def test_baseline_template_package_assets_success(monkeypatch):
    """验证现有 /public/template-package-assets 在 artifact 存在时可匿名读取内容。"""

    async def mock_get_asset_blob(self, artifact_id, file_hash):
        if artifact_id == "art-valid" and file_hash == "hash-valid":
            return {
                "content": b"mock-svg-bytes",
                "content_type": "image/svg+xml",
                "original_name": "icon.svg",
            }
        return None

    monkeypatch.setattr(RuntimeArtifactStore, "get_asset_blob", mock_get_asset_blob)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/public/template-package-assets/art-valid/hash-valid")
        assert response.status_code == 200
        assert response.content == b"mock-svg-bytes"
        assert "image/svg+xml" in response.headers.get("content-type", "")
