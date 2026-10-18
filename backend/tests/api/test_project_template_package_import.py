"""文件功能：验证项目模板包重复导入时主题预检保持幂等。"""

from __future__ import annotations

import io
import json
import zipfile

from app.db.session import get_session_factory
from app.models.page import Page
from httpx import AsyncClient
from sqlalchemy import select


async def test_project_template_package_second_import_should_reuse_branded_theme(
    authenticated_client: AsyncClient,
) -> None:
    """同一模板包第二次导入时，带 logo 的主题应复用而不是误报内容不同。"""

    source_workspace_id = await _create_workspace(authenticated_client, "模板主题源空间")
    logo_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "tpl_logo")
    invert_logo_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "tpl_invert_logo", stroke="#ffffff")
    icon_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "tpl_icon", stroke="#333333")
    theme_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/themes",
        json={
            "key": "tpl-theme",
            "name": "模板主题",
            "logo_asset_id": logo_asset["id"],
            "invert_logo_asset_id": invert_logo_asset["id"],
            "project_icon_asset_id": icon_asset["id"],
            "palette": _theme_palette(),
        },
    )
    assert theme_response.status_code == 200
    theme = theme_response.json()
    style_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/styles",
        json={
            "key": "tpl-style",
            "name": "模板样式",
            "configuration": {"presentation": {
                "page_width": 1600,
                "page_height": 900,
                "base_font_size": "18px",
                "icon_default_stroke_width": 2,
                "show_pdf_export_button": True,
                "menu_mode": "preview",
                "theme_key": theme["key"],
                "style_spec_markdown": "## 样式规范",
            }},
        },
    )
    assert style_response.status_code == 200
    style = style_response.json()
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": source_workspace_id,
            "name": "模板主题项目",
            "status": "active",
            "configuration": {"mode": "style", "style_id": style["id"]},
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": source_workspace_id,
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
        json={"metadata": {"slug": "tpl-theme-demo", "name": "模板主题演示"}, "refresh_screenshots": False},
    )
    assert export_response.status_code == 200
    archive_content = export_response.content

    with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
        theme_payload = json.loads(archive.read("themes/tpl-theme.json").decode("utf-8"))
    # 资源引用以 logo_asset_name 为准，包内不再重复写入 legacy 路径字段。
    assert theme_payload["logo_asset_name"] == "tpl_logo"
    assert theme_payload["logo_path"] is None
    assert theme_payload["invert_logo_path"] is None
    assert theme_payload["project_icon_name"] is None

    target_workspace_id = await _create_workspace(authenticated_client, "模板主题目标空间")
    first_import = await _import_template_package(authenticated_client, target_workspace_id, archive_content)
    assert first_import.status_code == 200

    second_validation = await _validate_template_package(authenticated_client, target_workspace_id, archive_content)
    assert second_validation["valid"] is True, second_validation["errors"]
    assert second_validation["themes"][0]["action"] == "reuse"

    second_import = await _import_template_package(authenticated_client, target_workspace_id, archive_content)
    assert second_import.status_code == 200


async def test_project_template_package_should_roundtrip_audio_reference(
    authenticated_client: AsyncClient,
) -> None:
    """模板包应携带页面引用的音频文件，并在目标工作空间重建同名资源绑定。"""

    source_workspace_id = await _create_workspace(authenticated_client, "模板音频源空间")
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": source_workspace_id, "name": "模板音频项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    audio_asset = await _upload_audio_asset(authenticated_client, source_workspace_id, "chapter_01")
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": source_workspace_id,
            "project_id": project_id,
            "title": "旁白页",
            "status": "active",
            "file_type": "vue",
            "page_content": '<template><AssetAudio name="chapter_01" purpose="content" class="w-full h-16" /></template>',
        },
    )
    assert page_response.status_code == 200, page_response.text

    export_response = await authenticated_client.post(
        f"/api/projects/{project_id}/template-package/export",
        json={"metadata": {"slug": "audio-template", "name": "音频模板"}, "refresh_screenshots": False},
    )
    assert export_response.status_code == 200, export_response.text

    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        audio_entries = [name for name in names if name.startswith("assets/") and name.endswith(".mp3")]
        assert audio_entries
        assert any(
            item["name"] == "chapter_01" and item["asset_type"] == "audio"
            for item in manifest["assets"]
        )
        page_payload = next(name for name in names if name.startswith("pages/") and name.endswith("/index.vue"))
        assert "AssetAudio" in archive.read(page_payload).decode("utf-8")

    target_workspace_id = await _create_workspace(authenticated_client, "模板音频目标空间")
    import_response = await _import_template_package(
        authenticated_client,
        target_workspace_id,
        export_response.content,
    )
    assert import_response.status_code == 200, import_response.text
    imported_project_id = import_response.json()["project_id"]

    target_assets = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/assets",
        params={"asset_type": "audio"},
    )
    assert target_assets.status_code == 200
    items = target_assets.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "chapter_01"
    assert items[0]["file_hash"] == audio_asset["file_hash"]

    async with get_session_factory()() as session:
        imported_pages = (
            await session.execute(select(Page).where(Page.project_id == imported_project_id))
        ).scalars().all()
    assert any('AssetAudio name="chapter_01"' in page.page_content for page in imported_pages)


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_svg_asset(
    client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    stroke: str = "#111111",
) -> dict:
    """创建用于主题引用的 SVG 图标资源。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": name,
            "original_name": f"{name}.svg",
            "content": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1h22" stroke="{stroke}"/></svg>',
            "tags": [],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _upload_audio_asset(client: AsyncClient, workspace_id: int, name: str) -> dict:
    """上传模板包测试使用的音频资源。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.mp3", b"template-audio-bytes", "audio/mpeg")},
        data={"asset_type": "audio", "tags": "[]", "name": name},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _validate_template_package(client: AsyncClient, workspace_id: int, content: bytes) -> dict:
    """提交项目模板包导入预检。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/template-packages/import/validate",
        files={"archive": ("template.zip", content, "application/zip")},
    )
    assert response.status_code == 200
    return response.json()


async def _import_template_package(client: AsyncClient, workspace_id: int, content: bytes):
    """提交项目模板包正式导入。"""

    return await client.post(
        f"/api/workspaces/{workspace_id}/template-packages/import",
        files={"archive": ("template.zip", content, "application/zip")},
    )


def _theme_palette() -> dict:
    """构造主题接口所需的最小色板。"""

    return {
        "text": {"primary": "#111111", "secondary": "#333333", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
        "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
        "accent": ["#2563eb"],
    }
