"""文件功能：验证项目模板包导出接口写入的模板 metadata 字段来源。"""

from __future__ import annotations

import io
import json
import zipfile

from httpx import AsyncClient

from app.services.capture_viewport_resolver import CaptureViewport
from app.services.page_preview_service import PagePreviewResult


async def test_project_template_export_should_use_current_user_and_skip_missing_project_metadata(
    authenticated_client: AsyncClient,
) -> None:
    """导出的 template metadata 应使用当前用户显示名，并排除项目没有维护的字段。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "模板导出工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "模板导出项目",
            "description": "项目描述",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "封面",
            "status": "active",
            "file_type": "vue",
            "page_content": "<template><main>封面</main></template>",
        },
    )
    assert page_response.status_code == 200

    export_response = await authenticated_client.post(
        f"/api/projects/{project_id}/template-package/export",
        json={
            "metadata": {
                "slug": "export-demo",
                "name": "导出演示模板",
                "summary": "摘要",
                "description": "说明",
            },
            "refresh_screenshots": False,
        },
    )
    assert export_response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        metadata = json.loads(archive.read("metadata/template.json").decode("utf-8"))

    assert metadata["slug"] == "export-demo"
    assert metadata["name"] == "导出演示模板"
    assert metadata["author"] == "平台系统管理员"
    assert not {
        "language",
        "license",
        "content_types",
        "style_keywords",
        "category",
        "tags",
    }.intersection(metadata)


async def test_project_template_export_should_wait_for_missing_page_screenshot(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面缺少截图时，导出应等待队列生成真实截图后再构建模板包。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "等待截图工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "等待截图项目",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "待截图封面",
            "status": "active",
            "file_type": "vue",
            "page_content": "<template><main>待截图封面</main></template>",
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()
    screenshot_content = b"template-export-real-screenshot"
    stored_objects: dict[str, bytes] = {}

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        target_page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ) -> PagePreviewResult:
        """返回无需真实 Runtime 服务的截图预览地址。"""

        return PagePreviewResult(
            file_path=f"src/views/{target_page.code}.vue",
            preview_url=f"http://runtime.local/__preview?ticket=template-export-{target_page.id}",
        )

    async def fake_capture_preview(  # noqa: ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,  # noqa: ANN001
    ) -> bytes:
        """返回可与占位 PNG 区分的截图内容。"""

        return screenshot_content

    async def fake_put_object(  # noqa: ANN001, ARG001
        self,
        storage_key: str,
        content: bytes,
        content_type: str | None = None,
        *,
        bucket_name: str | None = None,
    ) -> str:
        """在内存中保存截图对象，供导出阶段再次读取。"""

        stored_objects[storage_key] = content
        return storage_key

    async def fake_read_object(  # noqa: ANN001, ARG001
        self,
        storage_key: str,
        *,
        bucket_name: str | None = None,
    ) -> bytes:
        """读取测试内存中的截图对象。"""

        return stored_objects[storage_key]

    monkeypatch.setattr(
        "app.services.page_screenshot_service.PagePreviewService.create_page_preview",
        fake_create_page_preview,
    )
    monkeypatch.setattr(
        "app.services.page_screenshot_service.BrowserCaptureService.capture_preview",
        fake_capture_preview,
    )
    monkeypatch.setattr(
        "app.services.object_storage_service.ObjectStorageService.put_object",
        fake_put_object,
    )
    monkeypatch.setattr(
        "app.services.object_storage_service.ObjectStorageService.read_object",
        fake_read_object,
    )

    export_response = await authenticated_client.post(
        f"/api/projects/{project_id}/template-package/export",
        json={"refresh_screenshots": True},
    )
    assert export_response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        assert archive.read(f"screenshots/pages/{page['code']}.png") == screenshot_content
        assert archive.read("screenshots/cover.png") == screenshot_content
