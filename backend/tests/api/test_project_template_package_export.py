"""文件功能：验证项目模板包导出接口写入的模板 metadata 字段来源。"""

from __future__ import annotations

import io
import json
import zipfile

from httpx import AsyncClient


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
