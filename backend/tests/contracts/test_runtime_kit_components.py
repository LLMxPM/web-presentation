"""文件功能：验证 Runtime Kit 内建组件能力目录和只读预览 artifact。"""

from httpx import AsyncClient


async def create_workspace(authenticated_client: AsyncClient, name: str = "Runtime Kit 能力工作空间") -> int:
    """创建一个启用中的工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_runtime_kit_component_capability_list_should_expose_enabled_components(
    authenticated_client: AsyncClient,
) -> None:
    """Runtime Kit 能力目录应支持 kind/previewable 筛选并包含 doc-only 能力。"""

    asset_image_class = "w-full h-64 min-h-40 rounded-lg border border-border p-0 bg-transparent overflow-hidden"
    hidden_surface_props = {
        "width",
        "height",
        "minHeight",
        "backgroundColor",
        "showBorder",
        "borderRadius",
        "padding",
        "textColor",
        "highlightColor",
    }

    response = await authenticated_client.get("/api/runtime-kit/components")
    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    kinds = {item["kind"] for item in payload["items"]}

    assert payload["total"] >= 1
    assert "Icon.v1" in names
    assert "ThemeLogo.v1" in names
    assert "DefaultContainer.v1" in names
    assert "Connector.v1" in names
    assert "composable" in kinds
    assert payload["manifest_version"] == "1.0.0"
    assert all(item["name"] == f"{item['base_name']}.v{item['version_no']}" for item in payload["items"])

    previewable_response = await authenticated_client.get(
        "/api/runtime-kit/components",
        params={"kind": "component", "previewable": True},
    )
    assert previewable_response.status_code == 200
    previewable_items = previewable_response.json()["items"]
    assert all(item["kind"] == "component" for item in previewable_items)
    assert all(item["previewable"] is True for item in previewable_items)
    assert all(isinstance(item["preview_schema"], dict) and item["preview_schema"] for item in previewable_items)
    asset_image_item = next(item for item in previewable_items if item["name"] == "AssetImage.v1")
    assert asset_image_item["preview_schema"]["props"]["fallback"]["type"] == "string"
    assert asset_image_item["preview_schema"]["props"]["fallback"]["default"] == "图片资源无法渲染，请检查资源名称或资源内容。"
    assert asset_image_item["preview_schema"]["props"]["fallback"]["agent_visible"] is False
    assert asset_image_item["preview_schema"]["props"]["class"]["default"] == asset_image_class
    assert "外层图片框" in asset_image_item["preview_schema"]["props"]["class"]["description"]
    assert "边框框体内" in asset_image_item["preview_schema"]["props"]["fit"]["description"]
    assert "object-position" in asset_image_item["preview_schema"]["props"]["position"]["description"]
    assert any("fit 控制 object-fit" in item for item in asset_image_item["constraints"])
    assert not hidden_surface_props.intersection(asset_image_item["preview_schema"]["props"])
    assert "showFallbackPlaceholder" not in asset_image_item["preview_schema"]["props"]
    assert asset_image_item["preview_schema"]["presets"][0]["key"] == "contain-preview"
    assert asset_image_item["preview_options"]["page"]["width"] == 960
    icon_item = next(item for item in previewable_items if item["name"] == "Icon.v1")
    assert icon_item["preview_schema"]["props"]["class"]["default"] == "size-16"
    assert icon_item["preview_schema"]["props"]["strokeWidth"]["default"] == 2
    theme_logo_item = next(item for item in previewable_items if item["name"] == "ThemeLogo.v1")
    assert theme_logo_item["preview_schema"]["props"]["variant"]["default"] == "logo"
    assert theme_logo_item["preview_schema"]["props"]["size"]["default"] == 4
    assert "width" not in theme_logo_item["preview_schema"]["props"]
    assert "height" not in theme_logo_item["preview_schema"]["props"]
    assert "fit" not in theme_logo_item["preview_schema"]["props"]
    assert "fallbackSrc" not in theme_logo_item["preview_schema"]["props"]

    doc_only_response = await authenticated_client.get(
        "/api/runtime-kit/components",
        params={"kind": "composable", "keyword": "page"},
    )
    assert doc_only_response.status_code == 200
    doc_items = doc_only_response.json()["items"]
    doc_names = {item["name"] for item in doc_items}
    assert "usePageSize.v1" in doc_names
    use_page_size = next(item for item in doc_items if item["name"] == "usePageSize.v1")
    assert len(use_page_size["return_example"]) >= 1

    version_response = await authenticated_client.get(
        "/api/runtime-kit/components",
        params={"base_name": "Icon", "version_no": 1, "include_all_versions": True},
    )
    assert version_response.status_code == 200
    assert [item["name"] for item in version_response.json()["items"]] == ["Icon.v1"]


async def test_runtime_kit_component_preview_should_use_local_component_host(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """Runtime Kit 组件预览应通过本地 @runtime-kit 模块加载，artifact 不写入远程模块。"""

    workspace_id = await create_workspace(authenticated_client)
    preview_response = await authenticated_client.post(
        "/api/runtime-kit/components/Icon.v1/preview-artifacts",
        json={
            "workspace_id": workspace_id,
            "preview_options": {
                "page": {
                    "width": 640,
                    "height": 480,
                },
                "placement": {
                    "padding": 32,
                }
            },
        },
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["preview_kind"] == "component"
    assert preview_payload["component_source"] == "runtime_kit"
    assert preview_payload["runtime_kit_component_name"] == "Icon.v1"
    assert preview_payload["viewport_width"] == 640
    assert preview_payload["viewport_height"] == 480
    assert "component_version_no" not in preview_payload

    artifact_id = preview_payload["artifact_id"]
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["preview_kind"] == "component"
    assert manifest["owner_scope"]["scope_type"] == "runtime_kit_component"
    assert manifest["owner_scope"]["runtime_kit_component_name"] == "Icon.v1"
    assert manifest["modules"] == {}

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    component_preview = config_bundle_response.json()["component_preview"]
    assert component_preview["component_import_path"] == "@runtime-kit/public/components/primitives/Icon.v1.vue"
    assert component_preview["component_source"] == "runtime_kit"
    assert component_preview["runtime_kit_component_name"] == "Icon.v1"
    assert component_preview["schema"]["props"]["name"]["default"] == "home"
    assert component_preview["schema"]["props"]["class"]["default"] == "size-16"
    assert component_preview["schema"]["props"]["fallback"]["default"] == "?"
    assert component_preview["schema"]["presets"][1]["key"] == "fallback-icon"
    assert component_preview["placement"]["padding"] == 32


async def test_runtime_kit_asset_component_preview_should_include_manifest_schema(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """资源组件预览应把 manifest 中的 previewSchema 和默认预览选项下发给 Runtime。"""

    workspace_id = await create_workspace(authenticated_client, "Runtime Kit 资源组件工作空间")
    preview_response = await authenticated_client.post(
        "/api/runtime-kit/components/AssetImage.v1/preview-artifacts",
        json={"workspace_id": workspace_id},
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["runtime_kit_component_name"] == "AssetImage.v1"
    assert preview_payload["viewport_width"] == 960
    assert preview_payload["viewport_height"] == 540

    artifact_id = preview_payload["artifact_id"]
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    component_preview = config_bundle_response.json()["component_preview"]
    assert component_preview["component_import_path"] == "@runtime-kit/public/components/assets/AssetImage.v1.vue"
    assert component_preview["component_source"] == "runtime_kit"
    assert component_preview["schema"]["props"]["name"]["default"] == ""
    assert component_preview["schema"]["props"]["fallback"]["default"] == "图片资源无法渲染，请检查资源名称或资源内容。"
    assert component_preview["schema"]["props"]["fallback"]["agent_visible"] is False
    assert component_preview["schema"]["props"]["class"]["default"] == (
        "w-full h-64 min-h-40 rounded-lg border border-border p-0 bg-transparent overflow-hidden"
    )
    assert component_preview["schema"]["props"]["fit"]["default"] == "contain"
    assert "width" not in component_preview["schema"]["props"]
    assert "height" not in component_preview["schema"]["props"]
    assert "minHeight" not in component_preview["schema"]["props"]
    assert "showBorder" not in component_preview["schema"]["props"]
    assert "borderRadius" not in component_preview["schema"]["props"]
    assert "padding" not in component_preview["schema"]["props"]
    assert "backgroundColor" not in component_preview["schema"]["props"]
    assert "showFallbackPlaceholder" not in component_preview["schema"]["props"]
    assert component_preview["schema"]["presets"][1]["key"] == "cover-banner"
    assert component_preview["placement"]["width_value"] == 78
    assert component_preview["placement"]["padding"] == 56


async def test_runtime_kit_theme_logo_preview_should_include_manifest_schema(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """主题 Logo 组件预览应下发 manifest schema，且不提供兜底图片。"""

    workspace_id = await create_workspace(authenticated_client, "Runtime Kit 主题 Logo 工作空间")
    preview_response = await authenticated_client.post(
        "/api/runtime-kit/components/ThemeLogo.v1/preview-artifacts",
        json={"workspace_id": workspace_id},
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["runtime_kit_component_name"] == "ThemeLogo.v1"
    assert preview_payload["viewport_width"] == 640
    assert preview_payload["viewport_height"] == 360

    artifact_id = preview_payload["artifact_id"]
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    component_preview = config_bundle_response.json()["component_preview"]
    assert component_preview["component_import_path"] == "@runtime-kit/public/components/primitives/ThemeLogo.v1.vue"
    assert component_preview["component_source"] == "runtime_kit"
    assert component_preview["schema"]["props"]["variant"]["default"] == "logo"
    assert component_preview["schema"]["props"]["size"]["default"] == 4
    assert "width" not in component_preview["schema"]["props"]
    assert "height" not in component_preview["schema"]["props"]
    assert "fit" not in component_preview["schema"]["props"]
    assert "fallbackSrc" not in component_preview["schema"]["props"]
    assert component_preview["schema"]["presets"][1]["key"] == "theme-invert-logo"
    assert component_preview["placement"]["padding"] == 72


async def test_runtime_kit_default_container_preview_should_use_static_slot_defaults(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """内建容器组件预览应使用 manifest 中的静态 slot 默认内容。"""

    workspace_id = await create_workspace(authenticated_client, "Runtime Kit 容器组件工作空间")
    list_response = await authenticated_client.get(
        "/api/runtime-kit/components",
        params={"keyword": "页面根容器"},
    )
    assert list_response.status_code == 200
    container_item = next(item for item in list_response.json()["items"] if item["name"] == "DefaultContainer.v1")
    assert container_item["previewable"] is True
    assert container_item["preview_schema"]["slots"]["default"]["default"][0]["value"].find("Page Canvas") >= 0
    assert container_item["preview_schema"]["presets"][1]["key"] == "section-stack"
    assert any("定位上下文" in item for item in container_item["constraints"])

    preview_response = await authenticated_client.post(
        "/api/runtime-kit/components/DefaultContainer.v1/preview-artifacts",
        json={"workspace_id": workspace_id},
    )
    assert preview_response.status_code == 200

    artifact_id = preview_response.json()["artifact_id"]
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()
    component_preview = config_bundle["component_preview"]
    assert config_bundle["routes"] == {"routes": []}
    assert component_preview["component_import_path"] == (
        "@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue"
    )
    assert "Page Canvas" in component_preview["schema"]["slots"]["default"]["default"][0]["value"]
    assert component_preview["schema"]["presets"][0]["key"] == "center-canvas"


async def test_runtime_kit_component_preview_should_reject_disabled_or_unknown_component(
    authenticated_client: AsyncClient,
) -> None:
    """doc-only 或未知能力不能通过内建能力接口生成预览。"""

    workspace_id = await create_workspace(authenticated_client, "Runtime Kit 拒绝预览工作空间")
    response = await authenticated_client.post(
        "/api/runtime-kit/components/Connector.v1/preview-artifacts",
        json={"workspace_id": workspace_id},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "RUNTIME_KIT_CAPABILITY_PREVIEW_NOT_ALLOWED"

    not_found = await authenticated_client.post(
        "/api/runtime-kit/components/not_exists/preview-artifacts",
        json={"workspace_id": workspace_id},
    )
    assert not_found.status_code == 404
    assert not_found.json()["code"] == "RUNTIME_KIT_CAPABILITY_NOT_FOUND"
