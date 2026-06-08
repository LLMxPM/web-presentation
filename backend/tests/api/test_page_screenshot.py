"""文件功能：验证页面截图保存接口、响应字段和视口解析逻辑。"""

from __future__ import annotations

import asyncio
import io
import zipfile
from urllib.parse import quote, urlsplit

from httpx import AsyncClient

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.schemas.project_app_config import ProjectAppPageConfig
from app.services.browser_capture_service import BrowserCaptureJob, BrowserCaptureJobResult, BrowserCaptureService
from app.services.capture_viewport_resolver import CaptureViewport, CaptureViewportResolver
from app.services.page_screenshot_job_service import PageScreenshotJobService, run_page_screenshot_job
from app.services.page_preview_service import PagePreviewResult
from app.services.token_service import TokenService


async def _create_workspace_project(client: AsyncClient, name: str) -> tuple[int, int]:
    """创建截图测试页面所需的工作空间和项目。"""

    workspace_response = await client.post("/api/workspaces", json={"name": f"{name}空间", "status": "active"})
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": f"{name}项目", "status": "active"},
    )
    assert project_response.status_code == 200
    return workspace_id, project_response.json()["id"]


async def test_page_screenshot_should_save_and_expose_public_url(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """截图接口应保存截图元数据，并在详情与列表接口中返回公开地址。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "截图页面")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>screenshot</div></template>",
            "file_type": "vue",
            "title": "截图页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert create_response.status_code == 200
    page_data = create_response.json()

    captured: dict[str, object] = {}

    async def fake_create_page_preview(  # noqa: ANN001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        captured["preview_page_id"] = page.id
        captured["preview_user_id"] = user_id
        captured["asset_delivery_mode"] = asset_delivery_mode
        captured["asset_base_url_override"] = asset_base_url_override
        return PagePreviewResult(
            file_path=f"src/views/2026-04-02/{user_id}/{page.code}.vue",
            preview_url="http://runtime.local/__preview?ticket=demo",
        )

    async def fake_capture_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        captured["preview_url"] = preview_url
        captured["viewport"] = (viewport.width, viewport.height)
        captured["extra_http_headers"] = extra_http_headers
        return b"fake-png"

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:
        captured["storage_key"] = storage_key
        captured["content"] = content
        captured["content_type"] = content_type
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{page_data['id']}/screenshot",
        json={},
    )
    assert screenshot_response.status_code == 200
    screenshot_data = screenshot_response.json()
    assert captured["preview_page_id"] == page_data["id"]
    assert captured["preview_user_id"] == 1
    assert captured["asset_delivery_mode"] == "backend_cache"
    assert captured["asset_base_url_override"] == "http://127.0.0.1:8000"
    assert captured["preview_url"] == "http://runtime.local/__preview?ticket=demo"
    assert captured["viewport"] == (1920, 1080)
    assert captured["storage_key"] == f"page-screenshots/{page_data['code']}.png"
    assert captured["content"] == b"fake-png"
    assert captured["content_type"] == "image/png"
    expected_screenshot_url_prefix = f"http://127.0.0.1:8000/public/page-screenshots/{page_data['id']}?v="
    assert screenshot_data["screenshot_url"].startswith(expected_screenshot_url_prefix)
    assert screenshot_data["screenshot_url"].removeprefix(expected_screenshot_url_prefix).isdigit()
    assert screenshot_data["screenshot_version_no"] == screenshot_data["current_version_no"]
    assert isinstance(screenshot_data["screenshot_config_hash"], str)
    assert len(screenshot_data["screenshot_config_hash"]) == 64
    assert screenshot_data["screenshot_is_latest"] is True
    assert screenshot_data["screenshot_updated_at"] is not None

    detail_response = await authenticated_client.get(f"/api/pages/{page_data['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["screenshot_url"] == screenshot_data["screenshot_url"]
    assert detail_response.json()["screenshot_version_no"] == screenshot_data["current_version_no"]
    assert detail_response.json()["screenshot_config_hash"] == screenshot_data["screenshot_config_hash"]
    assert detail_response.json()["screenshot_is_latest"] is True

    list_response = await authenticated_client.get("/api/pages?page=1&page_size=10")
    assert list_response.status_code == 200
    listed_page = next(item for item in list_response.json()["items"] if item["id"] == page_data["id"])
    assert listed_page["screenshot_url"] == screenshot_data["screenshot_url"]
    assert listed_page["screenshot_version_no"] == screenshot_data["current_version_no"]
    assert listed_page["screenshot_config_hash"] == screenshot_data["screenshot_config_hash"]
    assert listed_page["screenshot_is_latest"] is True

    async def fake_read_object(self, storage_key: str) -> bytes:  # noqa: ARG001
        assert storage_key == f"page-screenshots/{page_data['code']}.png"
        return b"fake-png"

    monkeypatch.setattr("app.api.routes.public_assets.ObjectStorageService.read_object", fake_read_object)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.read_object", fake_read_object)
    screenshot_url_parts = urlsplit(screenshot_data["screenshot_url"])
    public_response = await authenticated_client.get(f"{screenshot_url_parts.path}?{screenshot_url_parts.query}")
    assert public_response.status_code == 200
    assert public_response.headers["content-type"] == "image/png"
    assert public_response.content == b"fake-png"

    download_response = await authenticated_client.get(f"{screenshot_url_parts.path}?{screenshot_url_parts.query}&download=1")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "image/png"
    assert download_response.headers["content-disposition"].startswith("attachment;")
    assert quote("截图页面-v1.png") in download_response.headers["content-disposition"]
    assert download_response.content == b"fake-png"

    archive_response = await authenticated_client.post(
        "/api/pages/batch-download-screenshots",
        json={"page_ids": [page_data["id"]]},
    )
    assert archive_response.status_code == 200
    assert archive_response.headers["content-type"] == "application/zip"
    assert archive_response.headers["content-disposition"] == 'attachment; filename="page-screenshots.zip"'
    with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
        assert archive.namelist() == ["01-截图页面-v1.png"]
        assert archive.read("01-截图页面-v1.png") == b"fake-png"


async def test_page_screenshot_should_be_marked_outdated_after_page_update(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面再次保存生成新版本后，旧截图应被标记为非最新。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "截图过期页面")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>v1</div></template>",
            "file_type": "vue",
            "title": "截图过期页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert create_response.status_code == 200
    page_data = create_response.json()

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        return PagePreviewResult(
            file_path=f"src/views/2026-04-02/{user_id}/{page.code}.vue",
            preview_url="http://runtime.local/__preview?ticket=outdated",
        )

    async def fake_capture_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        return b"outdated-png"

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{page_data['id']}/screenshot",
        json={},
    )
    assert screenshot_response.status_code == 200
    screenshot_data = screenshot_response.json()
    expected_screenshot_url_prefix = f"http://127.0.0.1:8000/public/page-screenshots/{page_data['id']}?v="
    assert screenshot_data["screenshot_url"].startswith(expected_screenshot_url_prefix)
    assert screenshot_data["screenshot_url"].removeprefix(expected_screenshot_url_prefix).isdigit()
    assert screenshot_data["screenshot_version_no"] == 1
    assert isinstance(screenshot_data["screenshot_config_hash"], str)
    assert screenshot_data["screenshot_is_latest"] is True

    update_response = await authenticated_client.patch(
        f"/api/pages/{page_data['id']}",
        json={
            "page_content": "<template><div>v2</div></template>",
            "file_type": "vue",
            "change_note": "更新页面内容",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 2
    assert update_response.json()["screenshot_url"] == screenshot_data["screenshot_url"]
    assert update_response.json()["screenshot_version_no"] == 1
    assert update_response.json()["screenshot_is_latest"] is False

    detail_response = await authenticated_client.get(f"/api/pages/{page_data['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["screenshot_url"] == screenshot_data["screenshot_url"]
    assert detail_response.json()["screenshot_version_no"] == 1
    assert detail_response.json()["current_version_no"] == 2
    assert detail_response.json()["screenshot_is_latest"] is False

    list_response = await authenticated_client.get("/api/pages?page=1&page_size=10")
    assert list_response.status_code == 200
    listed_page = next(item for item in list_response.json()["items"] if item["id"] == page_data["id"])
    assert listed_page["screenshot_url"] == screenshot_data["screenshot_url"]
    assert listed_page["screenshot_version_no"] == 1
    assert listed_page["current_version_no"] == 2
    assert listed_page["screenshot_is_latest"] is False


async def test_page_screenshot_should_be_marked_outdated_after_project_display_config_update(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """项目展示配置变化后，页面版本未变也应标记旧截图。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "截图配置工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "截图配置项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>display config</div></template>",
            "file_type": "vue",
            "title": "展示配置截图页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_data = page_response.json()

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        return PagePreviewResult(
            file_path=f"src/views/{page.code}.vue",
            preview_url="http://runtime.local/__preview?ticket=config",
        )

    async def fake_capture_preview(  # noqa: ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        return b"config-png"

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{page_data['id']}/screenshot",
        json={},
    )
    assert screenshot_response.status_code == 200
    screenshot_data = screenshot_response.json()
    assert screenshot_data["current_version_no"] == 1
    assert screenshot_data["screenshot_is_latest"] is True

    update_project_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"page_width": 1366, "page_height": 768},
    )
    assert update_project_response.status_code == 200

    detail_response = await authenticated_client.get(f"/api/pages/{page_data['id']}")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()
    assert detail_data["current_version_no"] == 1
    assert detail_data["screenshot_version_no"] == 1
    assert detail_data["screenshot_config_hash"] == screenshot_data["screenshot_config_hash"]
    assert detail_data["screenshot_is_latest"] is False


async def test_page_screenshot_should_prioritize_explicit_viewport(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """显式传入的截图视口应优先于系统默认值。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "视口页面")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>viewport</div></template>",
            "file_type": "vue",
            "title": "视口页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert create_response.status_code == 200

    captured: dict[str, object] = {}

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        return PagePreviewResult(
            file_path=f"src/views/2026-04-02/{user_id}/{page.code}.vue",
            preview_url="http://runtime.local/__preview?ticket=viewport",
        )

    async def fake_capture_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        captured["preview_url"] = preview_url
        captured["viewport"] = (viewport.width, viewport.height)
        captured["extra_http_headers"] = extra_http_headers
        return b"viewport-png"

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{create_response.json()['id']}/screenshot",
        json={"viewport_width": 1280, "viewport_height": 720},
    )
    assert screenshot_response.status_code == 200
    assert captured["preview_url"] == "http://runtime.local/__preview?ticket=viewport"
    assert captured["viewport"] == (1280, 720)


async def test_page_screenshot_should_reject_non_vue_page(
    authenticated_client: AsyncClient,
) -> None:
    """非 Vue 页面不应走 Runtime 预览截图链路。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "非 Vue 页面")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "export const foo = 1",
            "file_type": "ts",
            "title": "非 Vue 页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert create_response.status_code == 200

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{create_response.json()['id']}/screenshot",
        json={},
    )
    assert screenshot_response.status_code == 400
    assert screenshot_response.json()["code"] == "PAGE_SCREENSHOT_FILE_TYPE_UNSUPPORTED"


async def test_page_screenshot_preview_artifact_should_use_cached_asset_base(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
    monkeypatch,
) -> None:
    """截图链路创建的预览 artifact 应使用 Backend 缓存资源入口。"""

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "local")
    monkeypatch.setenv("BACKEND_PUBLIC_BASE_URL", "http://127.0.0.1:18080")
    monkeypatch.setenv("RUNTIME_PUBLIC_BASE_URL", "http://127.0.0.1:18080/runtime")
    get_settings.cache_clear()

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "截图缓存资源工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "截图缓存资源项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"cover-bytes", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>cached asset</div></template>",
            "file_type": "vue",
            "title": "截图缓存资源页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_data = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_data["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    captured: dict[str, object] = {}

    async def fake_capture_preview(  # noqa: ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        captured["preview_url"] = preview_url
        captured["extra_http_headers"] = extra_http_headers
        return b"cached-preview-png"

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{page_data['id']}/screenshot",
        json={},
    )
    assert screenshot_response.status_code == 200

    assert captured["preview_url"] == "http://127.0.0.1:7373/__preview"
    extra_http_headers = captured["extra_http_headers"]
    assert isinstance(extra_http_headers, dict)
    assert extra_http_headers["x-runtime-public-base-url"] == "http://127.0.0.1:7373/runtime"
    preview_claims = TokenService.verify_preview_context_token(extra_http_headers["x-runtime-preview-context"])
    artifact_id = str(preview_claims["artifact_id"])
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    assert manifest_response.json()["asset_base_url"] == f"http://127.0.0.1:8000/public/cached-assets/{workspace_id}"


async def test_page_screenshot_should_not_save_when_visual_assets_not_ready(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """视觉资源未就绪时截图接口应失败，并且不更新页面截图字段。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "视觉资源失败页面")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>asset not ready</div></template>",
            "file_type": "vue",
            "title": "视觉资源失败页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert create_response.status_code == 200
    page_data = create_response.json()
    captured = {"put_called": False}

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        return PagePreviewResult(
            file_path=f"src/views/{page.code}.vue",
            preview_url="http://runtime.local/__preview?ticket=asset-not-ready",
        )

    async def fake_capture_preview(  # noqa: ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        raise AppException(
            status_code=502,
            code="PAGE_SCREENSHOT_ASSET_NOT_READY",
            detail="页面视觉资源加载超时。",
        )

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        captured["put_called"] = True
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    screenshot_response = await authenticated_client.post(
        f"/api/pages/{page_data['id']}/screenshot",
        json={},
    )

    assert screenshot_response.status_code == 502
    assert screenshot_response.json()["code"] == "PAGE_SCREENSHOT_ASSET_NOT_READY"
    assert captured["put_called"] is False

    detail_response = await authenticated_client.get(f"/api/pages/{page_data['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["screenshot_url"] is None


async def test_page_screenshot_job_should_reuse_and_execute_pending_job(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """截图任务接口应复用同配置活跃任务，并可由队列执行器落库。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "截图任务页面")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>job</div></template>",
            "file_type": "vue",
            "title": "截图任务页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert create_response.status_code == 200
    page_data = create_response.json()

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        return PagePreviewResult(
            file_path=f"src/views/{page.code}.vue",
            preview_url=f"http://runtime.local/__preview?ticket=job-{page.id}",
        )

    async def fake_capture_preview(  # noqa: ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        return b"job-png"

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    job_response = await authenticated_client.post(f"/api/pages/{page_data['id']}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    job_data = job_response.json()
    assert job_data["status"] == "pending"
    assert job_data["page_id"] == page_data["id"]

    duplicate_response = await authenticated_client.post(f"/api/pages/{page_data['id']}/screenshot-jobs", json={})
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["id"] == job_data["id"]

    from app.db.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        claimed_jobs = await PageScreenshotJobService(session).claim_pending_jobs(limit=1)
        assert [job.id for job in claimed_jobs] == [job_data["id"]]

    await run_page_screenshot_job(job_data["id"], session_factory=session_factory)

    queried_response = await authenticated_client.get(f"/api/page-screenshot-jobs/{job_data['id']}")
    assert queried_response.status_code == 200
    assert queried_response.json()["status"] == "succeeded"

    detail_response = await authenticated_client.get(f"/api/pages/{page_data['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["screenshot_url"] is not None
    assert detail_response.json()["screenshot_is_latest"] is True


async def test_batch_refresh_page_screenshots_should_refresh_missing_and_outdated_screenshots(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """批量刷新应处理缺失或旧截图页面，且单页失败不阻断后续结果。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "批量截图工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "批量截图项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    page_ids: list[int] = []
    for title in ["批量页面 A", "批量页面 B", "无截图页面"]:
        page_response = await authenticated_client.post(
            "/api/pages",
            json={
                "page_content": f"<template><div>{title}</div></template>",
                "file_type": "vue",
                "title": title,
                "status": "active",
                "workspace_id": workspace_id,
                "project_id": project_id,
            },
        )
        assert page_response.status_code == 200
        page_ids.append(page_response.json()["id"])

    for ignored_page in [
        {"title": "归档 Vue 页面", "file_type": "vue", "status": "archived"},
        {"title": "脚本页面", "file_type": "ts", "status": "active"},
    ]:
        page_response = await authenticated_client.post(
            "/api/pages",
            json={
                "page_content": "<template><div>ignored</div></template>",
                "file_type": ignored_page["file_type"],
                "title": ignored_page["title"],
                "status": ignored_page["status"],
                "workspace_id": workspace_id,
                "project_id": project_id,
            },
        )
        assert page_response.status_code == 200

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ):
        return PagePreviewResult(
            file_path=f"src/views/{page.code}.vue",
            preview_url=f"http://runtime.local/__preview?ticket={page.id}",
        )

    async def fake_capture_preview(  # noqa: ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        return b"initial-png"

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)

    for page_id in page_ids[:2]:
        screenshot_response = await authenticated_client.post(f"/api/pages/{page_id}/screenshot", json={})
        assert screenshot_response.status_code == 200
        assert screenshot_response.json()["screenshot_is_latest"] is True

    update_project_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"base_font_size": "18px"},
    )
    assert update_project_response.status_code == 200

    captured_batch: dict[str, object] = {}

    async def fake_capture_preview_batch(self, jobs, *, max_concurrency=None):  # noqa: ANN001, ARG001
        captured_batch["job_count"] = len(jobs)
        captured_batch["max_concurrency"] = max_concurrency
        return [
            BrowserCaptureJobResult(
                key=job.key,
                error=AppException(status_code=502, code="PAGE_SCREENSHOT_CAPTURE_FAILED", detail="模拟截图失败。"),
            )
            if job.key == page_ids[1]
            else BrowserCaptureJobResult(key=job.key, content=b"batch-png")
            for job in jobs
        ]

    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview_batch", fake_capture_preview_batch)

    batch_response = await authenticated_client.post(
        "/api/pages/batch-refresh-screenshots",
        json={"project_id": project_id},
    )
    assert batch_response.status_code == 200
    batch_data = batch_response.json()
    assert captured_batch["job_count"] == 3
    assert captured_batch["max_concurrency"] == 2
    assert batch_data["requested_count"] == 3
    assert batch_data["succeeded_count"] == 2
    assert batch_data["failed_count"] == 1
    assert sorted(batch_data["page_ids"]) == sorted([page_ids[0], page_ids[2]])
    assert batch_data["failures"][0]["detail"] == "模拟截图失败。"

    success_page_response = await authenticated_client.get(f"/api/pages/{page_ids[0]}")
    assert success_page_response.status_code == 200
    assert success_page_response.json()["screenshot_is_latest"] is True

    created_screenshot_page_response = await authenticated_client.get(f"/api/pages/{page_ids[2]}")
    assert created_screenshot_page_response.status_code == 200
    assert created_screenshot_page_response.json()["screenshot_url"] is not None
    assert created_screenshot_page_response.json()["screenshot_is_latest"] is True


async def test_browser_capture_batch_should_isolate_single_job_failure(monkeypatch) -> None:
    """批量截图应限制并发，并把单项浏览器失败隔离为该任务结果。"""

    active_count = 0
    max_active_count = 0
    captured_headers: dict[str, object] = {}

    async def fake_capture_preview(
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        nonlocal active_count, max_active_count
        assert viewport.width == 320
        active_count += 1
        max_active_count = max(max_active_count, active_count)
        try:
            await asyncio.sleep(0.01)
            if preview_url.endswith("fail"):
                raise RuntimeError("模拟浏览器断连。")
            captured_headers[preview_url] = extra_http_headers
            return preview_url.encode("utf-8")
        finally:
            active_count -= 1

    monkeypatch.setattr(BrowserCaptureService, "capture_preview", fake_capture_preview)

    viewport = CaptureViewport(width=320, height=180)
    results = await BrowserCaptureService().capture_preview_batch(
        [
            BrowserCaptureJob(key=1, preview_url="http://runtime.local/ok-a", viewport=viewport, extra_http_headers={"x-demo": "a"}),
            BrowserCaptureJob(key=2, preview_url="http://runtime.local/fail", viewport=viewport),
            BrowserCaptureJob(key=3, preview_url="http://runtime.local/ok-b", viewport=viewport, extra_http_headers={"x-demo": "b"}),
        ],
        max_concurrency=2,
    )

    assert max_active_count == 2
    assert [result.key for result in results] == [1, 2, 3]
    assert results[0].content == b"http://runtime.local/ok-a"
    assert isinstance(results[1].error, AppException)
    assert results[1].error.code == "PAGE_SCREENSHOT_CAPTURE_FAILED"
    assert results[2].content == b"http://runtime.local/ok-b"
    assert captured_headers["http://runtime.local/ok-a"] == {"x-demo": "a"}
    assert captured_headers["http://runtime.local/ok-b"] == {"x-demo": "b"}


def test_capture_viewport_resolver_should_follow_explicit_project_default_priority(monkeypatch) -> None:
    """视口解析应遵循显式参数 > 项目配置 > 系统默认值的优先级。"""

    resolver = CaptureViewportResolver()
    page = type("FakePage", (), {"project_id": 1})()

    monkeypatch.setattr(
        resolver,
        "_resolve_project_viewport",
        lambda target_page, project_page_config=None: CaptureViewport(width=1600, height=900),  # noqa: ARG005
    )

    project_viewport = resolver.resolve(page)
    assert project_viewport.width == 1600
    assert project_viewport.height == 900

    explicit_viewport = resolver.resolve(page, viewport_width=1440, viewport_height=810)
    assert explicit_viewport.width == 1440
    assert explicit_viewport.height == 810


def test_capture_viewport_resolver_should_read_project_page_size() -> None:
    """当项目结构化配置声明页面尺寸时，截图视口应直接复用该尺寸。"""

    resolver = CaptureViewportResolver()
    page = type("FakePage", (), {"project_id": 9})()

    viewport = resolver.resolve(
        page,
        project_page_config=ProjectAppPageConfig(width=1366, height=768),
    )

    assert viewport.width == 1366
    assert viewport.height == 768
