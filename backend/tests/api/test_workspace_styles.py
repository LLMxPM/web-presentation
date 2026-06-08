"""文件功能：验证工作空间样式库接口与项目样式规范字段。"""

import hashlib
import io
import json
import zipfile

from httpx import AsyncClient

from app.schemas.project_app_config import DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN


async def test_workspace_styles_should_crud_copy_and_not_link_projects(authenticated_client: AsyncClient) -> None:
    """样式库应可维护复用数据，应用到项目后不与项目建立关联。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "样式工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    default_theme_key = workspace_response.json()["default_theme_key"]

    styles_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/styles")
    assert styles_response.status_code == 200
    default_style = styles_response.json()["items"][0]
    assert default_style["key"] == "default"
    assert default_style["theme_key"] == default_theme_key
    assert default_style["base_font_size"] == "20px"
    assert default_style["style_spec_markdown"] == DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN

    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/styles",
        json={
            "key": " Pitch ",
            "name": "路演样式",
            "description": "用于项目路演。",
            "page_width": 1600,
            "page_height": 900,
            "base_font_size": "18",
            "icon_default_stroke_width": 3,
            "show_pdf_export_button": False,
            "menu_mode": "bottom-preview",
            "theme_key": default_theme_key,
            "style_spec_markdown": "## 版式\r\n- 使用强标题。",
        },
    )
    assert create_response.status_code == 200
    style = create_response.json()
    style_id = style["id"]
    assert style["key"] == "pitch"
    assert style["base_font_size"] == "18px"
    assert style["style_spec_markdown"] == "## 版式\n- 使用强标题。"

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "已应用样式项目",
            "status": "active",
            "page_width": style["page_width"],
            "page_height": style["page_height"],
            "base_font_size": style["base_font_size"],
            "icon_default_stroke_width": style["icon_default_stroke_width"],
            "show_pdf_export_button": style["show_pdf_export_button"],
            "menu_mode": style["menu_mode"],
            "theme_key": style["theme_key"],
            "style_spec_markdown": style["style_spec_markdown"],
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    update_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/styles/{style_id}",
        json={
            "page_width": 1920,
            "theme_key": None,
            "style_spec_markdown": "## 新规范\r\n- 不影响项目。",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["page_width"] == 1920
    assert update_response.json()["theme_key"] is None
    assert update_response.json()["style_spec_markdown"] == "## 新规范\n- 不影响项目。"

    project_detail_response = await authenticated_client.get(f"/api/projects/{project_id}")
    assert project_detail_response.status_code == 200
    project_detail = project_detail_response.json()
    assert project_detail["page_width"] == 1600
    assert project_detail["theme_key"] == default_theme_key
    assert project_detail["style_spec_markdown"] == "## 版式\n- 使用强标题。"

    copy_response = await authenticated_client.post(f"/api/workspaces/{workspace_id}/styles/{style_id}/copy", json={})
    assert copy_response.status_code == 200
    assert copy_response.json()["key"].startswith("pitch_copy")

    delete_response = await authenticated_client.delete(f"/api/workspaces/{workspace_id}/styles/{style_id}")
    assert delete_response.status_code == 200


async def test_workspace_styles_should_validate_theme_scope(authenticated_client: AsyncClient) -> None:
    """样式引用的主题 key 必须属于当前工作空间。"""

    first_workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "样式主题空间 A", "status": "active"},
    )
    second_workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "样式主题空间 B", "status": "active"},
    )
    assert first_workspace_response.status_code == 200
    assert second_workspace_response.status_code == 200
    first_workspace_id = first_workspace_response.json()["id"]

    create_response = await authenticated_client.post(
        f"/api/workspaces/{first_workspace_id}/styles",
        json={
            "key": "invalid-theme",
            "name": "非法主题样式",
            "theme_key": "missing-theme",
        },
    )
    assert create_response.status_code == 400
    assert create_response.json()["code"] == "WORKSPACE_THEME_NOT_FOUND"


async def test_workspace_styles_should_reject_removed_icon_size_field(authenticated_client: AsyncClient) -> None:
    """样式接口不再接受独立默认图标尺寸字段。"""

    workspace_id = await _create_workspace(authenticated_client, "旧图标字段样式空间")
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/styles",
        json={"key": "legacy-icon-size", "name": "旧图标字段样式", "icon_default_size": 20},
    )

    assert response.status_code == 422


async def test_workspace_style_package_should_export_import_with_theme_dependencies(
    authenticated_client: AsyncClient,
) -> None:
    """样式离线包应携带引用主题、主题资源和字体配置，并可导入目标空间。"""

    source_workspace_id = await _create_workspace(authenticated_client, "样式包源空间")
    logo_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "style_pkg_logo")
    icon_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "style_pkg_icon", stroke="#222222")
    font_asset = await _upload_font_asset(authenticated_client, source_workspace_id, "style_pkg_font", b"font-content")
    font_config = await _create_font_config(authenticated_client, source_workspace_id, font_asset["id"], "PkgFont")
    theme = await _create_theme(
        authenticated_client,
        source_workspace_id,
        "style-pkg-theme",
        logo_asset_id=logo_asset["id"],
        project_icon_asset_id=icon_asset["id"],
        heading_font_id=font_config["id"],
    )
    style = await _create_style(authenticated_client, source_workspace_id, "style-pkg", theme["key"])
    suggested_component = await _create_published_component(
        authenticated_client,
        source_workspace_id,
        name="样式建议卡片",
        import_name="StyleSuggestedCard",
    )
    suggested_response = await authenticated_client.put(
        f"/api/workspaces/{source_workspace_id}/styles/{style['id']}/suggested-components",
        json={"component_ids": [suggested_component["id"]]},
    )
    assert suggested_response.status_code == 200

    export_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/styles/export-package",
        json={"style_ids": [style["id"]]},
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/zip"
    archive_content = export_response.content

    with zipfile.ZipFile(io.BytesIO(archive_content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "styles/style-pkg.json" in names
        assert "themes/style-pkg-theme.json" in names
        assert f"components/{suggested_component['code']}/component.json" in names
        assert f"components/{suggested_component['code']}/index.vue" in names
        style_payload = json.loads(archive.read("styles/style-pkg.json").decode("utf-8"))
        component_payload = json.loads(archive.read(f"components/{suggested_component['code']}/component.json").decode("utf-8"))
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["schema_version"] == 3
        assert manifest["styles"][0]["theme_key"] == "style-pkg-theme"
        assert manifest["styles"][0]["suggested_component_count"] == 1
        assert manifest["components"][0]["source_component_code"] == suggested_component["code"]
        assert isinstance(manifest["components"][0]["component_fingerprint"], str)
        assert isinstance(component_payload["component_fingerprint"], str)
        assert component_payload["fingerprint_schema_version"] == 1
        assert {item["name"] for item in manifest["assets"]} == {"style_pkg_logo", "style_pkg_icon", "style_pkg_font"}
        assert manifest["fonts"][0]["asset_name"] == "style_pkg_font"
        assert style_payload["style_spec_markdown"] == "## 样式规范\n- 保持标题突出。"
        assert style_payload["suggested_components"][0]["source_component_code"] == suggested_component["code"]

    reuse_validation = await _validate_style_package(authenticated_client, source_workspace_id, archive_content)
    assert reuse_validation["valid"] is True
    assert reuse_validation["styles"][0]["action"] == "overwrite"
    assert reuse_validation["styles"][0]["page_width"] == 1600
    assert reuse_validation["styles"][0]["page_height"] == 900
    assert reuse_validation["styles"][0]["base_font_size"] == "18px"
    assert reuse_validation["styles"][0]["show_pdf_export_button"] is True
    assert reuse_validation["styles"][0]["menu_mode"] == "preview"
    assert reuse_validation["styles"][0]["style_spec_markdown"] == "## 样式规范\n- 保持标题突出。"
    assert reuse_validation["components"][0]["action"] == "reuse"
    assert reuse_validation["themes"][0]["action"] == "reuse"
    assert {item["action"] for item in reuse_validation["assets"]} == {"reuse"}
    assert reuse_validation["fonts"][0]["action"] == "reuse"

    target_workspace_id = await _create_workspace(authenticated_client, "样式包目标空间")
    await _create_style(
        authenticated_client,
        target_workspace_id,
        "style-pkg",
        None,
        page_width=1280,
        style_spec_markdown="## 旧规范\n- 会被样式包覆盖。",
    )
    target_existing_component = await _create_published_component(
        authenticated_client,
        target_workspace_id,
        name="样式建议卡片",
        import_name="StyleSuggestedCard",
    )
    target_validation = await _validate_style_package(authenticated_client, target_workspace_id, archive_content)
    assert target_validation["valid"] is True
    assert target_validation["styles"][0]["action"] == "overwrite"
    assert target_validation["components"][0]["action"] == "reuse"
    assert target_validation["components"][0]["matched_component_code"] == target_existing_component["code"]
    import_response = await _import_style_package(authenticated_client, target_workspace_id, archive_content)
    assert import_response.status_code == 200
    assert import_response.json()["styles"][0]["action"] == "overwrite"
    assert import_response.json()["themes"][0]["action"] == "create"
    assert import_response.json()["components"][0]["action"] == "reuse"

    imported_styles_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/styles",
        params={"keyword": "style-pkg", "page": 1, "page_size": 10},
    )
    assert imported_styles_response.status_code == 200
    imported_style = imported_styles_response.json()["items"][0]
    assert imported_style["theme_key"] == "style-pkg-theme"
    assert imported_style["page_width"] == 1600
    assert imported_style["style_spec_markdown"] == "## 样式规范\n- 保持标题突出。"
    imported_suggested_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/styles/{imported_style['id']}/suggested-components",
    )
    assert imported_suggested_response.status_code == 200
    imported_suggested = imported_suggested_response.json()["items"]
    assert [item["import_name"] for item in imported_suggested] == ["StyleSuggestedCard"]
    assert imported_suggested[0]["code"] == target_existing_component["code"]

    imported_themes_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/themes",
        params={"keyword": "style-pkg-theme", "page": 1, "page_size": 10},
    )
    assert imported_themes_response.status_code == 200
    imported_theme = imported_themes_response.json()["items"][0]
    assert imported_theme["logo_asset"]["name"] == "style_pkg_logo"
    assert imported_theme["project_icon_asset"]["name"] == "style_pkg_icon"
    assert imported_theme["heading_font"]["asset_name"] == "style_pkg_font"


async def test_workspace_style_package_export_should_warn_for_suggested_component_dynamic_assets(
    authenticated_client: AsyncClient,
) -> None:
    """样式包导出遇到建议组件动态资源时应 warning，并允许手动补充资源。"""

    source_workspace_id = await _create_workspace(authenticated_client, "样式动态资源源空间")
    style = await _create_style(authenticated_client, source_workspace_id, "dynamic-style", None)
    manual_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "style_manual_asset")
    suggested_component = await _create_published_component(
        authenticated_client,
        source_workspace_id,
        name="动态建议组件",
        import_name="DynamicSuggestedCard",
        content=(
            "<template>"
            '<AssetImage :name="props.runtimeAssetName" />'
            "</template>"
            "<script setup>const props = defineProps({ runtimeAssetName: String })</script>"
        ),
    )
    suggested_response = await authenticated_client.put(
        f"/api/workspaces/{source_workspace_id}/styles/{style['id']}/suggested-components",
        json={"component_ids": [suggested_component["id"]]},
    )
    assert suggested_response.status_code == 200

    validate_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/styles/export-package/validate",
        json={"style_ids": [style["id"]], "manual_asset_names": ["style_manual_asset"]},
    )
    assert validate_response.status_code == 200
    validation = validate_response.json()
    assert validation["can_export"] is True
    assert validation["dynamic_resource_components"] == ["动态建议组件"]
    assert {item["name"] for item in validation["manual_assets"]} == {"style_manual_asset"}
    assert validation["warnings"]

    export_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/styles/export-package",
        json={"style_ids": [style["id"]], "manual_asset_names": ["style_manual_asset"]},
    )
    assert export_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        component_payload = json.loads(archive.read(f"components/{suggested_component['code']}/component.json").decode("utf-8"))
        assert manifest["export_warnings"]
        assert manifest["manual_asset_names"] == ["style_manual_asset"]
        assert manifest["dynamic_resource_components"] == ["动态建议组件"]
        assert {item["name"] for item in manifest["assets"]} == {"style_manual_asset"}
        assert component_payload["asset_names"] == []
        assert f"assets/{manual_asset['file_hash']}/asset.json" in archive.namelist()

    target_workspace_id = await _create_workspace(authenticated_client, "样式动态资源目标空间")
    import_validation = await _validate_style_package(authenticated_client, target_workspace_id, export_response.content)
    assert import_validation["valid"] is True
    assert import_validation["warnings"] == manifest["export_warnings"]


async def test_workspace_style_package_should_overwrite_style_and_reject_dependency_conflicts(
    authenticated_client: AsyncClient,
) -> None:
    """导入预检应允许同 key 样式覆盖，但拒绝主题、资源和字体配置冲突。"""

    source_workspace_id = await _create_workspace(authenticated_client, "样式包冲突源空间")
    logo_asset = await _create_svg_asset(authenticated_client, source_workspace_id, "conflict_logo", stroke="#111111")
    font_asset = await _upload_font_asset(authenticated_client, source_workspace_id, "conflict_font", b"same-font-content")
    font_config = await _create_font_config(authenticated_client, source_workspace_id, font_asset["id"], "ConflictFont")
    theme = await _create_theme(
        authenticated_client,
        source_workspace_id,
        "conflict-theme",
        logo_asset_id=logo_asset["id"],
        heading_font_id=font_config["id"],
    )
    style = await _create_style(authenticated_client, source_workspace_id, "conflict-style", theme["key"])
    archive_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/styles/export-package",
        json={"style_ids": [style["id"]]},
    )
    assert archive_response.status_code == 200

    target_workspace_id = await _create_workspace(authenticated_client, "样式包冲突目标空间")
    conflict_logo = await _create_svg_asset(authenticated_client, target_workspace_id, "conflict_logo", stroke="#222222")
    target_font_asset = await _upload_font_asset(authenticated_client, target_workspace_id, "conflict_font", b"same-font-content")
    await _create_font_config(authenticated_client, target_workspace_id, target_font_asset["id"], "OtherFont")
    await _create_theme(authenticated_client, target_workspace_id, "conflict-theme", logo_asset_id=conflict_logo["id"])
    await _create_style(authenticated_client, target_workspace_id, "conflict-style", None, page_width=1280)

    validation = await _validate_style_package(authenticated_client, target_workspace_id, archive_response.content)
    assert validation["valid"] is False
    assert validation["styles"][0]["action"] == "overwrite"
    assert any("资源 \"conflict_logo\"" in error for error in validation["errors"])
    assert any("字体 \"conflict_font\"" in error for error in validation["errors"])
    assert any("主题 \"conflict-theme\"" in error for error in validation["errors"])


async def test_workspace_style_package_should_allow_style_without_theme(
    authenticated_client: AsyncClient,
) -> None:
    """未绑定主题的样式应可导出导入，包内不应强制包含主题。"""

    source_workspace_id = await _create_workspace(authenticated_client, "无主题样式源空间")
    style = await _create_style(authenticated_client, source_workspace_id, "no-theme-style", None)
    export_response = await authenticated_client.post(
        f"/api/workspaces/{source_workspace_id}/styles/export-package",
        json={"style_ids": [style["id"]]},
    )
    assert export_response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["themes"] == []

    target_workspace_id = await _create_workspace(authenticated_client, "无主题样式目标空间")
    import_response = await _import_style_package(authenticated_client, target_workspace_id, export_response.content)
    assert import_response.status_code == 200
    assert import_response.json()["themes"] == []

    styles_response = await authenticated_client.get(
        f"/api/workspaces/{target_workspace_id}/styles",
        params={"keyword": "no-theme-style", "page": 1, "page_size": 10},
    )
    assert styles_response.status_code == 200
    assert styles_response.json()["items"][0]["theme_key"] is None


async def test_workspace_style_package_should_reject_legacy_schema_version(
    authenticated_client: AsyncClient,
) -> None:
    """旧 v2 样式包不再兼容导入。"""

    target_workspace_id = await _create_workspace(authenticated_client, "旧样式包目标空间")
    archive_content = _build_zip(
        {
            "manifest.json": json.dumps(
                {
                    "schema_version": 2,
                    "styles": [{"key": "legacy-style", "name": "旧样式", "theme_key": None}],
                    "themes": [],
                    "assets": [],
                    "fonts": [],
                }
            ),
            "styles/legacy-style.json": json.dumps(
                {
                    "key": "legacy-style",
                    "name": "旧样式",
                    "description": "旧包未携带样式规范。",
                    "page_width": 1920,
                    "page_height": 1080,
                    "base_font_size": "16px",
                    "icon_default_size": 20,
                    "icon_default_stroke_width": 2,
                    "show_pdf_export_button": True,
                    "menu_mode": "preview",
                    "theme_key": None,
                }
            ),
            "fonts/font-configs.json": "[]",
        }
    )

    validation_response = await _post_style_package_validation(authenticated_client, target_workspace_id, archive_content)
    assert validation_response.status_code == 200
    assert validation_response.json()["valid"] is False
    assert any("schema_version" in error for error in validation_response.json()["errors"])

    import_response = await _import_style_package(authenticated_client, target_workspace_id, archive_content)
    assert import_response.status_code == 400


async def test_workspace_style_package_should_reject_invalid_archives(authenticated_client: AsyncClient) -> None:
    """样式离线包预检应拒绝非 Zip、缺少 manifest、非法路径和缺少必需文件的包。"""

    workspace_id = await _create_workspace(authenticated_client, "样式包非法空间")

    non_zip_response = await _post_style_package_validation(authenticated_client, workspace_id, b"not zip")
    assert non_zip_response.status_code == 400
    assert non_zip_response.json()["code"] == "WORKSPACE_STYLE_PACKAGE_INVALID"

    missing_manifest = _build_zip({"styles/demo.json": "{}"})
    missing_manifest_response = await _post_style_package_validation(authenticated_client, workspace_id, missing_manifest)
    assert missing_manifest_response.status_code == 400
    assert missing_manifest_response.json()["code"] == "WORKSPACE_STYLE_PACKAGE_INVALID"

    invalid_path = _build_zip({"../manifest.json": "{}"})
    invalid_path_response = await _post_style_package_validation(authenticated_client, workspace_id, invalid_path)
    assert invalid_path_response.status_code == 400
    assert invalid_path_response.json()["code"] == "WORKSPACE_STYLE_PACKAGE_PATH_INVALID"

    asset_hash = hashlib.sha256(b"missing-file").hexdigest()
    missing_asset_file = _build_zip(
        {
            "manifest.json": json.dumps({
                "schema_version": 1,
                "styles": [],
                "themes": [],
                "assets": [{"name": "missing", "original_name": "missing.svg", "asset_type": "icon", "file_hash": asset_hash}],
                "fonts": [],
            }),
            f"assets/{asset_hash}/asset.json": json.dumps(
                {
                    "name": "missing",
                    "original_name": "missing.svg",
                    "asset_type": "icon",
                    "file_hash": asset_hash,
                }
            ),
            "fonts/font-configs.json": "[]",
        }
    )
    missing_asset_file_response = await _post_style_package_validation(authenticated_client, workspace_id, missing_asset_file)
    assert missing_asset_file_response.status_code == 400
    assert missing_asset_file_response.json()["code"] == "WORKSPACE_STYLE_PACKAGE_INVALID"


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


async def _upload_font_asset(client: AsyncClient, workspace_id: int, name: str, content: bytes) -> dict:
    """上传字体资源。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        data={"asset_type": "font", "tags": "[]", "name": name},
        files={"file": (f"{name}.woff2", content, "font/woff2")},
    )
    assert response.status_code == 200
    return response.json()


async def _create_font_config(client: AsyncClient, workspace_id: int, asset_id: int, font_family: str) -> dict:
    """创建字体配置。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": font_family,
            "font_format": "woff2",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert response.status_code == 200
    return response.json()


async def _create_theme(
    client: AsyncClient,
    workspace_id: int,
    key: str,
    *,
    logo_asset_id: int | None = None,
    project_icon_asset_id: int | None = None,
    heading_font_id: int | None = None,
) -> dict:
    """创建测试主题。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": key,
            "name": f"{key} 主题",
            "logo_asset_id": logo_asset_id,
            "project_icon_asset_id": project_icon_asset_id,
            "heading_font_id": heading_font_id,
            "palette": _theme_palette(),
        },
    )
    assert response.status_code == 200
    return response.json()


async def _create_style(
    client: AsyncClient,
    workspace_id: int,
    key: str,
    theme_key: str | None,
    *,
    page_width: int = 1600,
    style_spec_markdown: str = "## 样式规范\n- 保持标题突出。",
) -> dict:
    """创建测试样式。"""

    response = await client.post(
        f"/api/workspaces/{workspace_id}/styles",
        json={
            "key": key,
            "name": f"{key} 样式",
            "description": "离线包测试样式。",
            "page_width": page_width,
            "page_height": 900,
            "base_font_size": "18px",
            "icon_default_stroke_width": 2,
            "show_pdf_export_button": True,
            "menu_mode": "preview",
            "theme_key": theme_key,
            "style_spec_markdown": style_spec_markdown,
        },
    )
    assert response.status_code == 200
    return response.json()


async def _create_published_component(
    client: AsyncClient,
    workspace_id: int,
    *,
    name: str,
    import_name: str,
    content: str | None = None,
) -> dict:
    """创建并发布用于样式包建议组件测试的工作空间组件。"""

    create_response = await client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": name,
            "import_name": import_name,
            "component_type": "内容区块",
            "content": content or f"<template><section>{name}</section></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": "样式包导出版", "change_note": "用于样式包导出。"},
    )
    assert publish_response.status_code == 200
    return publish_response.json()


async def _validate_style_package(client: AsyncClient, workspace_id: int, archive_content: bytes) -> dict:
    """调用样式离线包预检接口。"""

    response = await _post_style_package_validation(client, workspace_id, archive_content)
    assert response.status_code == 200
    return response.json()


async def _post_style_package_validation(client: AsyncClient, workspace_id: int, archive_content: bytes):
    """提交样式离线包预检请求。"""

    return await client.post(
        f"/api/workspaces/{workspace_id}/styles/import-package/validate",
        files={"archive": ("workspace-styles.zip", archive_content, "application/zip")},
    )


async def _import_style_package(client: AsyncClient, workspace_id: int, archive_content: bytes):
    """调用样式离线包正式导入接口。"""

    return await client.post(
        f"/api/workspaces/{workspace_id}/styles/import-package",
        files={"archive": ("workspace-styles.zip", archive_content, "application/zip")},
    )


def _build_zip(entries: dict[str, str]) -> bytes:
    """按给定条目构造 Zip 字节。"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _theme_palette() -> dict:
    """构造主题接口所需的最小色板。"""

    return {
        "text": {"primary": "#111111", "secondary": "#333333", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
        "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
        "accent": ["#2563eb"],
    }
