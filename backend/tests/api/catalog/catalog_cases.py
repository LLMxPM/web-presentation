"""文件功能：验证工作空间、项目和页面资源库的 CRUD 及编码自动生成。"""

import io
import json
import re
import zipfile
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.schemas.project_app_config import DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


async def _create_catalog_workspace(client: AsyncClient, name: str) -> dict:
    """创建测试工作空间并返回响应 JSON。"""

    response = await client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()


async def _create_catalog_svg_asset(client: AsyncClient, workspace_id: int, name: str) -> dict:
    """创建组件分享包测试使用的 SVG 资源。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": name,
            "original_name": f"{name}.svg",
            "content": (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                f"<title>{name}</title><path d=\"M2 2h20v20H2z\"/>"
                "</svg>"
            ),
            "tags": [],
        },
    )
    assert response.status_code == 200
    return response.json()


def _rewrite_zip_json(archive_content: bytes, target_name: str, rewrite) -> bytes:
    """重写 Zip 内指定 JSON 文件，保留其它条目不变。"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive_content)) as source_archive:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target_archive:
            for item in source_archive.infolist():
                content = source_archive.read(item.filename)
                if item.filename == target_name:
                    payload = json.loads(content.decode("utf-8"))
                    content = json.dumps(rewrite(payload), ensure_ascii=False).encode("utf-8")
                target_archive.writestr(item, content)
    return buffer.getvalue()


async def _create_catalog_project(
    client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    status: str = "active",
) -> dict:
    """创建测试项目并返回响应 JSON。"""

    response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": status},
    )
    assert response.status_code == 200
    return response.json()


async def _create_catalog_page(
    client: AsyncClient,
    workspace_id: int,
    project_id: int,
    title: str,
    *,
    page_content: str = "<template><div>copy-page</div></template>",
    summary: str | None = None,
    speaker_notes: str | None = None,
    status: str = "active",
) -> dict:
    """创建测试页面并返回响应 JSON。"""

    response = await client.post(
        "/api/pages",
        json={
            "page_content": page_content,
            "file_type": "vue",
            "title": title,
            "summary": summary,
            "speaker_notes": speaker_notes,
            "status": status,
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert response.status_code == 200
    return response.json()

__all__ = [name for name in globals() if not name.startswith("__")]
