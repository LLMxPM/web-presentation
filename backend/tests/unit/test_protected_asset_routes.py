"""文件功能：测试受保护资源与素材端点，验证权限检查、快照约束、ETag 304、HEAD 与 Range。"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db_session
from app.main import app
from app.models.asset import WorkspaceAsset
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService


@pytest.fixture
def mock_session():
    """提供轻量模拟的 AsyncSession。"""
    session = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_preview_protected_asset_blob_success_and_304(monkeypatch):
    """测试通过预览票据读取模板包 blob 临时素材，以及 ETag 304 缓存条件请求。"""

    artifact_id = "art-test-123"
    file_hash = "hash-blob-456"

    # 1. 构造合法预览票据
    token = TokenService.generate_preview_context_token(
        artifact_id=artifact_id,
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-test",
        tenant_id="tenant_1",
        expires_in_seconds=300,
    )

    manifest = {
        "assets": {"icons/test.svg": file_hash},
        "asset_metadata": {},
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    async def mock_get_asset_blob(self, aid, fhash):
        if aid == artifact_id and fhash == file_hash:
            return {
                "content": b"<svg>test</svg>",
                "content_type": "image/svg+xml",
                "original_name": "test.svg",
            }
        return None

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)
    monkeypatch.setattr(RuntimeArtifactStore, "get_asset_blob", mock_get_asset_blob)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. 正常 GET 读取
        resp = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.content == b"<svg>test</svg>"
        assert resp.headers["Cache-Control"] == "private, no-cache"
        assert resp.headers["ETag"] == f'"{file_hash}"'
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

        # 3. 带 If-None-Match 命中 304
        resp_304 = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": token},
            headers={"If-None-Match": f'"{file_hash}"'},
        )
        assert resp_304.status_code == 304
        assert resp_304.headers["Cache-Control"] == "private, no-cache"
        assert resp_304.content == b""

        # 4. HEAD 请求
        resp_head = await client.head(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": token},
        )
        assert resp_head.status_code == 200
        assert resp_head.content == b""
        assert resp_head.headers["Content-Length"] == str(len(b"<svg>test</svg>"))

        # 5. Range 请求
        resp_range = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": token},
            headers={"Range": "bytes=0-4"},
        )
        assert resp_range.status_code == 206
        assert resp_range.content == b"<svg>"
        assert resp_range.headers["Content-Range"] == f"bytes 0-4/{len(b'<svg>test</svg>')}"


@pytest.mark.asyncio
async def test_preview_protected_asset_unauthorized_cases(monkeypatch):
    """测试预览素材端点对缺失票据、跨 artifact 票据及快照外资源的拦截。"""

    artifact_id = "art-test-123"
    file_hash = "hash-legit"

    manifest = {
        "assets": {"logo.png": file_hash},
        "asset_metadata": {},
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 缺 token -> 401 FILE_ACCESS_REQUIRED
        resp1 = await client.get(f"/preview/artifacts/{artifact_id}/assets/{file_hash}")
        assert resp1.status_code == 401
        assert resp1.json()["code"] == "FILE_ACCESS_REQUIRED"
        assert resp1.headers["Cache-Control"] == "no-store"

        # 2. 跨 artifact 票据 -> 403 FILE_ACCESS_SCOPE_MISMATCH
        other_token = TokenService.generate_preview_context_token(
            artifact_id="other-artifact-999",
            preview_kind="project",
            scope_type="project",
            workspace_id=1,
            entry_descriptor={"entry_type": "route", "route": "/"},
            asset_base_url="/assets",
            trace_id="tr-test",
            tenant_id="tenant_1",
            expires_in_seconds=300,
        )
        resp2 = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": other_token},
        )
        assert resp2.status_code == 403
        assert resp2.json()["code"] == "FILE_ACCESS_SCOPE_MISMATCH"

        # 3. 请求非快照内资源 -> 404 FILE_NOT_FOUND
        legit_token = TokenService.generate_preview_context_token(
            artifact_id=artifact_id,
            preview_kind="project",
            scope_type="project",
            workspace_id=1,
            entry_descriptor={"entry_type": "route", "route": "/"},
            asset_base_url="/assets",
            trace_id="tr-test",
            tenant_id="tenant_1",
            expires_in_seconds=300,
        )
        resp3 = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/unauthorized-hash",
            params={"token": legit_token},
        )
        assert resp3.status_code == 404
        assert resp3.json()["code"] == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_internal_runtime_protected_asset_success(monkeypatch):
    """测试通过 Runtime 服务凭证回源读取受保护素材。"""

    artifact_id = "art-internal-1"
    file_hash = "hash-int-1"

    service_token = TokenService.generate_runtime_service_access_token(
        artifact_id=artifact_id,
        expires_in_seconds=300,
    )

    manifest = {
        "assets": {"icon.svg": file_hash},
        "asset_metadata": {},
    }

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    async def mock_get_asset_blob(self, aid, fhash):
        if aid == artifact_id and fhash == file_hash:
            return {
                "content": b"internal-data",
                "content_type": "text/plain",
                "original_name": "data.txt",
            }
        return None

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)
    monkeypatch.setattr(RuntimeArtifactStore, "get_asset_blob", mock_get_asset_blob)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/internal/runtime/preview-artifacts/{artifact_id}/assets/{file_hash}",
            headers={"Authorization": f"Bearer {service_token}"},
        )
        assert resp.status_code == 200
        assert resp.content == b"internal-data"
        assert resp.headers["Cache-Control"] == "private, no-cache"


@pytest.mark.asyncio
async def test_preview_protected_asset_if_range_handling(monkeypatch):
    """测试 If-Range 条件判断：ETag 匹配时返回 206，ETag 不匹配时忽略 Range 返回完整 200。"""

    artifact_id = "art-if-range"
    file_hash = "hash-current-ver"

    token = TokenService.generate_preview_context_token(
        artifact_id=artifact_id,
        preview_kind="project",
        scope_type="project",
        workspace_id=1,
        entry_descriptor={"entry_type": "route", "route": "/"},
        asset_base_url="/assets",
        trace_id="tr-test",
        tenant_id="tenant_1",
        expires_in_seconds=300,
    )

    manifest = {"assets": {"video.mp4": file_hash}}

    async def mock_get_manifest(self, aid):
        return manifest if aid == artifact_id else None

    async def mock_get_asset_blob(self, aid, fhash):
        if aid == artifact_id and fhash == file_hash:
            return {
                "content": b"0123456789abcdef",
                "content_type": "video/mp4",
                "original_name": "video.mp4",
            }
        return None

    monkeypatch.setattr(RuntimeArtifactStore, "get_manifest", mock_get_manifest)
    monkeypatch.setattr(RuntimeArtifactStore, "get_asset_blob", mock_get_asset_blob)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. If-Range 匹配：返回 206
        resp_match = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": token},
            headers={"Range": "bytes=0-3", "If-Range": f'"{file_hash}"'},
        )
        assert resp_match.status_code == 206
        assert resp_match.content == b"0123"

        # 2. If-Range 不匹配（例如旧版本 ETag）：忽略 Range，返回完整内容 200
        resp_mismatch = await client.get(
            f"/preview/artifacts/{artifact_id}/assets/{file_hash}",
            params={"token": token},
            headers={"Range": "bytes=0-3", "If-Range": '"old-version-etag"'},
        )
        assert resp_mismatch.status_code == 200
        assert resp_mismatch.content == b"0123456789abcdef"


@pytest.mark.asyncio
async def test_editor_page_screenshot_content(monkeypatch, tmp_path):
    """测试 Editor 页面受保护截图读取端点：验证 get_model ORM 属性、latest 访问与流式交付。"""

    from app.api.dependencies import get_current_user
    from app.services.auth_service import AuthContext
    from app.models.user import User
    from app.models.page import Page
    from app.services.page_service import PageService
    from app.services.object_storage_service import ObjectStorageService
    from contextlib import asynccontextmanager

    user = User(
        id=1,
        username="editor_user",
        display_name="Editor User",
        password_hash="fake",
        preview_size_presets={},
    )
    mock_auth = AuthContext(user=user, session_token="session-token", backend_session_id="bsid-1")

    mock_page = Page(
        id=101,
        workspace_id=1,
        project_id=2,
        code="slide-101",
        title="Slide 101",
        screenshot_storage_key="page-screenshots/101/v1/conf/1920x1080.png",
    )

    test_png = b"\x89PNG\r\n\x1a\nscreenshot-for-editor"
    screenshot_file = tmp_path / "slide-101.png"
    screenshot_file.write_bytes(test_png)

    @asynccontextmanager
    async def mock_open_object(self, storage_key, **kwargs):
        yield screenshot_file

    app.dependency_overrides[get_current_user] = lambda: mock_auth

    try:
        monkeypatch.setattr(PageService, "get_model", AsyncMock(return_value=mock_page))
        monkeypatch.setattr(ObjectStorageService, "open_object_for_read", mock_open_object)
        monkeypatch.setattr(ObjectStorageService, "read_object", AsyncMock(return_value=test_png))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/pages/101/screenshots/latest/content")
            assert resp.status_code == 200
            assert resp.content == test_png
            assert resp.headers["Cache-Control"] == "private, no-cache"
            etag = resp.headers["ETag"]

            # 条件请求 304
            resp_304 = await client.get(
                "/api/pages/101/screenshots/latest/content",
                headers={"If-None-Match": etag},
            )
            assert resp_304.status_code == 304

            # 未知 ID 返回 404
            resp_404 = await client.get("/api/pages/101/screenshots/not-exist-shot/content")
            assert resp_404.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
