"""文件功能：验证组件预览页面与占位选项的新契约。"""

from httpx import AsyncClient


async def test_workspace_should_not_expose_component_preview_default_config(
    authenticated_client: AsyncClient,
) -> None:
    """工作空间响应不再包含独立组件预览默认配置。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "无组件预览默认配置工作空间", "status": "active"},
    )
    assert response.status_code == 200
    assert "component_preview_default_config" not in response.json()

    detail_response = await authenticated_client.get(f"/api/workspaces/{response.json()['id']}")
    assert detail_response.status_code == 200
    assert "component_preview_default_config" not in detail_response.json()


async def test_component_preview_options_should_drive_page_and_placement(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """草稿组件预览应使用 preview_options 生成页面尺寸和组件占位。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件预览选项工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    preview_response = await authenticated_client.post(
        "/api/components/preview-artifacts/from-source",
        json={
            "workspace_id": workspace_id,
            "component_name": "选项组件",
            "content": "<template><section>preview options</section></template>",
            "file_type": "vue",
            "preview_options": {
                "page": {
                    "width": 1280,
                    "height": 720,
                    "base_font_size": "18",
                    "icon_default_stroke_width": 3,
                },
                "placement": {
                    "width_mode": "fixed",
                    "width_value": 640,
                    "height_mode": "percent",
                    "height_value": 50,
                    "horizontal_align": "end",
                    "vertical_align": "start",
                    "padding": 24,
                },
            },
        },
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["viewport_width"] == 1280
    assert preview_response.json()["viewport_height"] == 720

    artifact_id = preview_response.json()["artifact_id"]
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()
    assert config_bundle["app"]["app"]["page"] == {
        "width": 1280,
        "height": 720,
        "baseFontSize": "18px",
        "iconDefaultStrokeWidth": 3,
    }
    assert "canvas" not in config_bundle["component_preview"]
    assert config_bundle["component_preview"]["placement"] == {
        "width_mode": "fixed",
        "width_value": 640,
        "height_mode": "percent",
        "height_value": 50,
        "horizontal_align": "end",
        "vertical_align": "start",
        "padding": 24,
    }


async def test_component_preview_options_should_reject_removed_icon_size_field(
    authenticated_client: AsyncClient,
) -> None:
    """组件预览页面配置不再接受独立默认图标尺寸。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件预览旧图标字段空间", "status": "active"},
    )
    assert workspace_response.status_code == 200

    preview_response = await authenticated_client.post(
        "/api/components/preview-artifacts/from-source",
        json={
            "workspace_id": workspace_response.json()["id"],
            "component_name": "旧字段组件",
            "content": "<template><section>legacy icon size</section></template>",
            "file_type": "vue",
            "preview_options": {
                "page": {
                    "icon_default_size": 28,
                },
            },
        },
    )

    assert preview_response.status_code == 422
