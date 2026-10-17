"""文件功能：单元测试 External API v1 受保护文件端点（资产文件、页面截图与构建 ZIP 归档）。"""

from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies_external import ExternalAuthContext, get_external_auth_context
from app.db.session import get_db_session
from app.main import app
from app.models.asset import WorkspaceAsset
from app.models.page import Page
from app.models.workspace import Project
from app.models.project_build_job import ProjectBuildJob
from app.models.user import User
from app.services.asset_service import AssetService
from app.services.object_storage_service import ObjectStorageService
from app.services.page_service import PageService
from app.services.project_build_service import ProjectBuildService
from app.services.project_service import ProjectService


@pytest.fixture
def mock_auth():
    """提供测试用 ExternalAuthContext。"""
    user = User(
        id=1,
        username="external_test_user",
        display_name="External User",
        password_hash="fake",
        preview_size_presets={},
    )
    auth = ExternalAuthContext(
        user=user,
        token=None,  # type: ignore
        token_id=1,
        token_public_id="pat_test_123",
        all_workspaces=True,
        workspace_ids={1},
        scopes={
            "asset:read",
            "page:read",
            "project:read",
        },
    )
    return auth


@pytest.mark.asyncio
async def test_external_asset_file_download_and_304(mock_auth, monkeypatch):
    """测试 External API 资产文件读取端点：验证 200、ETag、304 缓存和 HEAD。"""

    mock_session = AsyncMock()
    mock_auth_ensure = AsyncMock()
    monkeypatch.setattr(ExternalAuthContext, "ensure_workspace_access", mock_auth_ensure)

    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_external_auth_context] = lambda: mock_auth

    try:
        mock_asset = WorkspaceAsset(
            id=10,
            workspace_id=1,
            name="logo",
            file_name="logo.png",
            original_name="logo.png",
            content_type="image/png",
            file_size=17,
            file_hash="hash-png-12345",
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(b"\x89PNG\r\n\x1a\nfakeimage")
            temp_asset_path = Path(tf.name)

        try:
            from contextlib import asynccontextmanager

            class MockDriver:
                @asynccontextmanager
                async def open_for_read(self, *args, **kwargs):
                    yield temp_asset_path

            from app.services import asset_service as asset_service_module
            from app.services import asset_storage_drivers

            monkeypatch.setattr(AssetService, "get_asset_or_raise", AsyncMock(return_value=mock_asset))
            monkeypatch.setattr(asset_storage_drivers, "get_driver", lambda: MockDriver())
            monkeypatch.setattr(asset_service_module, "get_driver", lambda: MockDriver())

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {
                    "Authorization": "Bearer pat_test_123",
                    "X-Workspace-ID": "1",
                }

                # 1. 正常 GET 下载
                resp = await client.get("/api/v1/assets/10/file", headers=headers)
                assert resp.status_code == 200
                assert resp.content == b"\x89PNG\r\n\x1a\nfakeimage"
                assert resp.headers["Cache-Control"] == "private, no-cache"
                assert resp.headers["ETag"] == '"hash-png-12345"'
                assert resp.headers["X-Content-Type-Options"] == "nosniff"

                # 2. 携带 If-None-Match 命中 304
                resp_304 = await client.get(
                    "/api/v1/assets/10/file",
                    headers={**headers, "If-None-Match": '"hash-png-12345"'},
                )
                assert resp_304.status_code == 304
                assert resp_304.headers["Cache-Control"] == "private, no-cache"
                assert resp_304.content == b""

                # 3. HEAD 请求
                resp_head = await client.head("/api/v1/assets/10/file", headers=headers)
                assert resp_head.status_code == 200
                assert resp_head.content == b""
                assert resp_head.headers["Content-Length"] == str(len(b"\x89PNG\r\n\x1a\nfakeimage"))
        finally:
            if temp_asset_path.exists():
                temp_asset_path.unlink()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_external_auth_context, None)


@pytest.mark.asyncio
async def test_external_page_screenshot_content(mock_auth, monkeypatch):
    """测试 External API 读取页面截图端点。"""

    mock_session = AsyncMock()
    mock_auth_ensure = AsyncMock()
    monkeypatch.setattr(ExternalAuthContext, "ensure_workspace_access", mock_auth_ensure)

    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_external_auth_context] = lambda: mock_auth

    try:
        mock_page = Page(
            id=5,
            workspace_id=1,
            project_id=2,
            code="cover-slide",
            title="Cover",
            screenshot_storage_key="page-screenshots/5/v1/conf/1920x1080.png",
        )

        from app.schemas.page import PageItem, PageFileType, RecordStatus
        from datetime import datetime

        dummy_page_item = PageItem(
            id=5,
            code="cover-slide",
            file_type=PageFileType.VUE,
            title="Cover",
            summary=None,
            page_content="<template><div></div></template>",
            current_version_no=1,
            status=RecordStatus.ACTIVE,
            workspace_id=1,
            project_id=2,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            created_by=1,
            updated_by=1,
        )

        async def mock_get(self, page_id, user_id=None):
            return dummy_page_item

        async def mock_get_model(self, page_id, user_id=None):
            return mock_page

        screenshot_bytes = b"\x89PNG\r\n\x1a\npng-screenshot-binary-data"

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(screenshot_bytes)
            temp_screenshot_path = Path(tf.name)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_open_object(self, storage_key, **kwargs):
            yield temp_screenshot_path

        monkeypatch.setattr(PageService, "get", mock_get)
        monkeypatch.setattr(PageService, "get_model", mock_get_model)
        monkeypatch.setattr(ObjectStorageService, "open_object_for_read", mock_open_object)
        monkeypatch.setattr(ObjectStorageService, "read_object", AsyncMock(return_value=screenshot_bytes))

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {
                    "Authorization": "Bearer pat_test_123",
                    "X-Workspace-ID": "1",
                }

                # 1. 正常读取 latest 截图
                resp = await client.get("/api/v1/pages/5/screenshots/latest/content", headers=headers)
                assert resp.status_code == 200
                assert resp.content == screenshot_bytes
                assert resp.headers["Cache-Control"] == "private, no-cache"
                etag = resp.headers["ETag"]

                # 2. 条件请求 304
                resp_304 = await client.get(
                    "/api/v1/pages/5/screenshots/latest/content",
                    headers={**headers, "If-None-Match": etag},
                )
                assert resp_304.status_code == 304
                assert resp_304.content == b""

                # 3. HEAD
                resp_head = await client.head("/api/v1/pages/5/screenshots/latest/content", headers=headers)
                assert resp_head.status_code == 200
                assert resp_head.content == b""

                # 4. 未知 screenshot_id 返回 404
                resp_404 = await client.get("/api/v1/pages/5/screenshots/unknown-id/content", headers=headers)
                assert resp_404.status_code == 404
        finally:
            if temp_screenshot_path.exists():
                temp_screenshot_path.unlink()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_external_auth_context, None)


@pytest.mark.asyncio
async def test_external_project_build_artifact_download(mock_auth, monkeypatch):
    """测试 External API 下载项目构建 ZIP 产物。"""

    mock_session = AsyncMock()
    mock_auth_ensure = AsyncMock()
    monkeypatch.setattr(ExternalAuthContext, "ensure_workspace_access", mock_auth_ensure)

    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_external_auth_context] = lambda: mock_auth

    try:
        mock_job = ProjectBuildJob(
            id=7,
            project_id=2,
            snapshot_release_id=3,
            base_url="./",
            status="success",
            artifact_storage_key="builds/p2-job7.zip",
            artifact_sha256="fake-sha256-zip",
            artifact_size_bytes=18,
        )
        mock_project = Project(
            id=2,
            workspace_id=1,
            code="test-proj",
            name="Test Proj",
        )

        async def mock_get_job(self, project_id, job_id):
            return mock_job

        async def mock_get_project(self, project_id, user_id=None):
            return mock_project

        monkeypatch.setattr(ProjectBuildService, "get_job_by_project_and_id", mock_get_job)
        monkeypatch.setattr(ProjectService, "get", mock_get_project)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tf.write(b"PK\x03\x04fake-zip-archive")
            temp_zip_path = Path(tf.name)

        try:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def mock_open_object(self, storage_key, **kwargs):
                yield temp_zip_path

            monkeypatch.setattr(ObjectStorageService, "open_object_for_read", mock_open_object)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                headers = {
                    "Authorization": "Bearer pat_test_123",
                    "X-Workspace-ID": "1",
                }

                # 1. GET 下载 ZIP 产物
                resp = await client.get("/api/v1/projects/2/build-jobs/7/artifact", headers=headers)
                assert resp.status_code == 200
                assert resp.content == b"PK\x03\x04fake-zip-archive"
                assert resp.headers["Cache-Control"] == "no-store"
                assert "attachment" in resp.headers["Content-Disposition"]

                # 2. HEAD 请求
                resp_head = await client.head("/api/v1/projects/2/build-jobs/7/artifact", headers=headers)
                assert resp_head.status_code == 200
                assert resp_head.content == b""
                assert resp_head.headers["Cache-Control"] == "no-store"
                assert resp_head.headers["Content-Length"] == "18"
        finally:
            if temp_zip_path.exists():
                temp_zip_path.unlink()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_external_auth_context, None)


@pytest.mark.asyncio
async def test_external_file_routes_workspace_isolation(mock_auth, monkeypatch):
    """测试 External API 严格校验工作空间归属：页面截图与构建产物跨工作空间请求必须返回 404。"""
    mock_session = AsyncMock()
    mock_auth_ensure = AsyncMock()
    monkeypatch.setattr(ExternalAuthContext, "ensure_workspace_access", mock_auth_ensure)

    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_external_auth_context] = lambda: mock_auth

    try:
        # mock 页面归属于 workspace_id=999
        mock_page = Page(id=5, workspace_id=999, project_id=2, code="cover", title="Cover")
        monkeypatch.setattr(PageService, "get_model", AsyncMock(return_value=mock_page))

        # mock 项目归属于 workspace_id=999
        mock_job = ProjectBuildJob(id=7, project_id=2, status="success", artifact_storage_key="builds/p2-job7.zip")
        mock_project = Project(id=2, workspace_id=999, name="Test Project", code="test-proj")
        monkeypatch.setattr(ProjectBuildService, "get_job_by_project_and_id", AsyncMock(return_value=mock_job))
        monkeypatch.setattr(ProjectService, "get", AsyncMock(return_value=mock_project))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "Authorization": "Bearer pat_test_123",
                "X-Workspace-ID": "1",  # 声明操作工作空间 1，但资源属于 999
            }
            # 1. 跨工作空间请求页面截图返回 404
            resp_page = await client.get("/api/v1/pages/5/screenshots/latest/content", headers=headers)
            assert resp_page.status_code == 404
            assert resp_page.json()["code"] == "PAGE_NOT_FOUND"

            # 2. 跨工作空间请求构建产物返回 404
            resp_build = await client.get("/api/v1/projects/2/build-jobs/7/artifact", headers=headers)
            assert resp_build.status_code == 404
            assert resp_build.json()["code"] == "PROJECT_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_external_auth_context, None)

