"""文件功能：验证工作空间主题库接口的 key 归一化与引用级联更新行为。"""

import yaml

from httpx import AsyncClient


async def test_workspace_theme_update_should_normalize_key_and_cascade_references(
    authenticated_client: AsyncClient,
) -> None:
    """编辑主题时应把 key 归一化为小写，并同步更新工作空间默认主题引用。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_id = themes_response.json()["items"][0]["id"]

    update_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={"key": " LightBlue_New "},
    )

    assert update_response.status_code == 200
    assert update_response.json()["key"] == "lightblue_new"

    workspace_detail_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}")
    assert workspace_detail_response.status_code == 200
    assert workspace_detail_response.json()["default_theme_key"] == "lightblue_new"


async def test_workspace_theme_response_should_not_expose_page_visual_specs(
    authenticated_client: AsyncClient,
) -> None:
    """主题详情不再暴露项目页面字号与图标规格字段。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题页面规格剥离工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    themes_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes")
    assert themes_response.status_code == 200
    theme_item = themes_response.json()["items"][0]
    theme_id = theme_item["id"]
    assert "base_font_size" not in theme_item
    assert "icon_default_size" not in theme_item
    assert "icon_default_stroke_width" not in theme_item

    detail_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes/{theme_id}")
    assert detail_response.status_code == 200
    assert "base_font_size" not in detail_response.json()
    assert "icon_default_size" not in detail_response.json()
    assert "icon_default_stroke_width" not in detail_response.json()

    update_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={"base_font_size": "18"},
    )
    assert update_response.status_code == 200
    assert "base_font_size" not in update_response.json()


async def test_workspace_theme_delete_should_hard_delete_theme(authenticated_client: AsyncClient) -> None:
    """删除未被引用的主题时，应直接删除数据库记录并释放资源外键引用。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题硬删除空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    icon_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "hard_delete_theme_icon",
            "original_name": "hard_delete_theme_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
            "tags": [],
        },
    )
    assert icon_response.status_code == 200

    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "hard-delete-theme",
            "name": "硬删除主题",
            "project_icon_asset_id": icon_response.json()["id"],
            "palette": _theme_palette(),
        },
    )
    assert theme_response.status_code == 200
    theme_id = theme_response.json()["id"]

    delete_response = await authenticated_client.delete(f"/api/workspaces/{workspace_id}/themes/{theme_id}")
    assert delete_response.status_code == 200

    detail_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/themes/{theme_id}")
    assert detail_response.status_code == 404

    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{icon_response.json()['id']}/archive",
        json={"archive_reason": "验证主题硬删除释放资源外键"},
    )
    assert archive_response.status_code == 200

    asset_delete_response = await authenticated_client.delete(
        f"/api/workspaces/{workspace_id}/assets/{icon_response.json()['id']}",
    )
    assert asset_delete_response.status_code == 204


async def test_workspace_theme_create_without_fonts_should_use_browser_default_labels(authenticated_client: AsyncClient) -> None:
    """创建主题不绑定字体时，应输出浏览器默认字体标签。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题空字体创建空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "browser-default-font",
            "name": "浏览器默认字体主题",
            "palette": _theme_palette(),
        },
    )

    assert theme_response.status_code == 200
    theme_item = theme_response.json()
    assert theme_item["heading_font_id"] is None
    assert theme_item["body_font_id"] is None
    assert theme_item["code_font_id"] is None
    assert theme_item["heading_font_label"] == "system-ui"
    assert theme_item["body_font_label"] == "system-ui"
    assert theme_item["code_font_label"] == "monospace"

    resolved_config = yaml.safe_load(theme_item["resolved_theme_config_yaml"])
    assert resolved_config["themes"]["browser-default-font"]["typography"] == {
        "headingfont": "system-ui",
        "bodyfont": "system-ui",
        "codefont": "monospace",
    }


async def test_workspace_theme_update_should_preserve_omitted_fonts_and_reset_explicit_null(
    authenticated_client: AsyncClient,
) -> None:
    """编辑主题未传字体字段应保留绑定，显式传 null 时应切回浏览器默认字体。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题字体清空空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    font_asset = await _upload_font_asset(authenticated_client, workspace_id, "theme_update_font", b"font-content")
    font_config = await _create_font_config(authenticated_client, workspace_id, font_asset["id"], "ThemeUpdateFont")

    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "clearable-font-theme",
            "name": "可清空字体主题",
            "heading_font_id": font_config["id"],
            "body_font_id": font_config["id"],
            "code_font_id": font_config["id"],
            "palette": _theme_palette(),
        },
    )
    assert theme_response.status_code == 200
    theme_id = theme_response.json()["id"]

    preserved_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={"name": "可清空字体主题改名"},
    )
    assert preserved_response.status_code == 200
    assert preserved_response.json()["heading_font_id"] == font_config["id"]
    assert preserved_response.json()["body_font_id"] == font_config["id"]
    assert preserved_response.json()["code_font_id"] == font_config["id"]
    assert preserved_response.json()["heading_font_label"] == "ThemeUpdateFont"
    assert preserved_response.json()["body_font_label"] == "ThemeUpdateFont"
    assert preserved_response.json()["code_font_label"] == "ThemeUpdateFont"

    cleared_response = await authenticated_client.patch(
        f"/api/workspaces/{workspace_id}/themes/{theme_id}",
        json={
            "heading_font_id": None,
            "body_font_id": None,
            "code_font_id": None,
        },
    )
    assert cleared_response.status_code == 200
    cleared_theme = cleared_response.json()
    assert cleared_theme["heading_font_id"] is None
    assert cleared_theme["body_font_id"] is None
    assert cleared_theme["code_font_id"] is None
    assert cleared_theme["heading_font_label"] == "system-ui"
    assert cleared_theme["body_font_label"] == "system-ui"
    assert cleared_theme["code_font_label"] == "monospace"

    resolved_config = yaml.safe_load(cleared_theme["resolved_theme_config_yaml"])
    assert resolved_config["themes"]["clearable-font-theme"]["typography"] == {
        "headingfont": "system-ui",
        "bodyfont": "system-ui",
        "codefont": "monospace",
    }


def _theme_palette() -> dict:
    """构造主题接口所需的最小色板。"""

    return {
        "text": {"primary": "#111111", "secondary": "#333333", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#111111"},
        "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
        "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
        "accent": ["#2563eb"],
    }


async def _upload_font_asset(authenticated_client: AsyncClient, workspace_id: int, name: str, content: bytes) -> dict:
    """上传字体资源并返回资产响应。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (f"{name}.woff2", content, "font/woff2")},
        data={"asset_type": "font", "name": name, "tags": "[]"},
    )
    assert response.status_code == 200
    return response.json()


async def _create_font_config(authenticated_client: AsyncClient, workspace_id: int, asset_id: int, font_family: str) -> dict:
    """注册字体配置并返回接口响应。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_id,
            "font_family": font_family,
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert response.status_code == 200
    return response.json()
