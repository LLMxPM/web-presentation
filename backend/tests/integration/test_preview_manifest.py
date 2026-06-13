"""文件功能：验证项目与页面预览 artifact 清单中的资源映射和入口转换逻辑。"""

from httpx import AsyncClient


async def test_preview_artifact_manifest_should_map_asset_name_to_file_hash(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """预览 artifact 清单应写入 asset.name -> file_hash 映射，供 Runtime 严格按逻辑名解析资源。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "预览资源映射工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "预览资源映射项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("Top.svg", b"<svg><path d='M0 0'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    uploaded_asset = upload_response.json()
    assert uploaded_asset["name"] == "Top"
    assert uploaded_asset["original_name"] == "Top.svg"
    file_hash = uploaded_asset["file_hash"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-icon'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>asset-page</div></template>",
            "file_type": "vue",
            "title": "资源映射页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()

    assert manifest["artifact_kind"] == "preview_artifact"
    assert manifest["asset_base_url"] == f"http://127.0.0.1:8000/public/assets/{workspace_id}"
    assert manifest["assets"]["Top"] == file_hash
    assert manifest["asset_metadata"]["Top"]["render_type"] == "icon"
    assert manifest["asset_metadata"]["Top"]["asset_role"] == "foundation"
    assert manifest["asset_metadata"]["Top"]["content_type"] == "image/svg+xml"
    assert "Top.svg" not in manifest["assets"]


async def test_preview_artifact_manifest_should_reject_request_without_runtime_service_token(
    authenticated_client: AsyncClient,
) -> None:
    """内部 preview artifact 接口缺少 Runtime 服务令牌时应直接拒绝访问。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "预览鉴权工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "预览鉴权项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-auth'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>auth-page</div></template>",
            "file_type": "vue",
            "title": "鉴权页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
    )
    assert manifest_response.status_code == 401
    assert manifest_response.json()["code"] == "RUNTIME_SERVICE_TOKEN_REQUIRED"


async def test_page_version_preview_artifact_should_use_historical_page_content(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """历史版本单页预览应以内存物化后的版本源码与备注作为入口内容。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "历史预览工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "历史预览项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>历史版本 V1</div></template>",
            "file_type": "vue",
            "title": "历史版本页面",
            "speaker_notes": "历史版本 V1 备注",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "history",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    update_response = await authenticated_client.patch(
        f"/api/pages/{page['id']}",
        json={
            "page_content": "<template><div>当前版本 V2</div></template>",
            "file_type": "vue",
            "speaker_notes": "当前版本 V2 备注",
            "change_note": "更新到 V2",
        },
    )
    assert update_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/pages/{page['id']}/versions/1/preview-artifact",
    )
    assert preview_response.status_code == 200
    preview_data = preview_response.json()
    artifact_id = preview_data["artifact_id"]
    module_path = f"src/views/{page['code']}.vue"

    assert preview_data["preview_kind"] == "page"
    assert preview_data["entry_descriptor"] == {
        "entry_type": "module",
        "module_path": module_path,
    }

    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["preview_kind"] == "page"
    assert manifest["entry_descriptor"]["module_path"] == module_path

    module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": module_path},
        headers=runtime_service_headers,
    )
    assert module_response.status_code == 200
    assert module_response.text == "<template><div>历史版本 V1</div></template>"

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    assert config_bundle_response.json()["routes"]["routes"][0]["meta"]["speakerNotes"] == "历史版本 V1 备注"


async def test_asset_upload_should_generate_default_name_and_support_manual_override(
    authenticated_client: AsyncClient,
) -> None:
    """资源上传应默认按文件名去后缀生成 name，并允许显式覆盖。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "资源命名工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    default_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("Brand.Mark.svg", b"<svg><path d='M0 0'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert default_upload_response.status_code == 200
    assert default_upload_response.json()["name"] == "Brand"

    custom_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("hero-banner.png", b"fake-png", "image/png")},
        data={"asset_type": "image", "tags": "[]", "name": "homepage-hero"},
    )
    assert custom_upload_response.status_code == 200
    assert custom_upload_response.json()["name"] == "homepage-hero"
    assert custom_upload_response.json()["original_name"] == "hero-banner.png"


async def test_asset_upload_should_reject_duplicate_name_in_same_workspace(
    authenticated_client: AsyncClient,
) -> None:
    """同一工作空间内资源 name 必须唯一，不区分资产类型。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "资源重名工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    first_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("duplicate-name.svg", b"<svg><path d='M0 0'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert first_upload_response.status_code == 200
    assert first_upload_response.json()["name"] == "duplicate-name"

    second_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("duplicate-name.ttf", b"font-data", "font/ttf")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert second_upload_response.status_code == 409
    assert second_upload_response.json()["code"] == "ASSET_NAME_CONFLICT"


async def test_preview_artifact_config_bundle_should_translate_routes_to_component_paths(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """预览 artifact 配置包应把结构化项目路由转译成 Runtime 可加载的 component 路径。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "预览路由工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "预览路由项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-route'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-page</div></template>",
            "file_type": "vue",
            "title": "路由页面",
            "speaker_notes": "演讲时说明路由页面备注。",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    update_project_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert update_project_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()

    assert config_bundle["routes"]["routes"] == [
        {
            "route": "home",
            "component": f"@/views/{page['code']}.vue",
            "meta": {
                "title": "路由页面",
                "order": 0,
                "hidden": False,
                "speakerNotes": "演讲时说明路由页面备注。",
            },
        }
    ]


async def test_preview_artifact_should_return_viewport_from_project_page_config(
    authenticated_client: AsyncClient,
) -> None:
    """预览 artifact 返回值应携带项目结构化页面配置声明的尺寸。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "预览尺寸工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "预览尺寸项目",
            "status": "active",
            "page_width": 1600,
            "page_height": 900,
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-viewport'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>viewport-page</div></template>",
            "file_type": "vue",
            "title": "尺寸页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    preview_data = preview_response.json()

    assert preview_data["viewport_width"] == 1600
    assert preview_data["viewport_height"] == 900


async def test_project_preview_artifact_should_default_to_first_visible_route_when_entry_descriptor_missing(
    authenticated_client: AsyncClient,
) -> None:
    """整项目预览未显式指定入口时，应由后端自动选择首个可见页面路由。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "默认预览路由工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "默认预览路由项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-default-route'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    hidden_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>hidden-page</div></template>",
            "file_type": "vue",
            "title": "隐藏页",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert hidden_page_response.status_code == 200

    visible_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>visible-page</div></template>",
            "file_type": "vue",
            "title": "可见页",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert visible_page_response.status_code == 200

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "hidden",
                    "order": 0,
                    "hidden": True,
                    "page_id": hidden_page_response.json()["id"],
                },
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 1,
                    "hidden": False,
                    "page_id": visible_page_response.json()["id"],
                },
            ]
        },
    )
    assert route_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={},
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["entry_descriptor"] == {
        "entry_type": "route",
        "route": "/home",
    }


async def test_project_preview_artifact_should_accept_group_route_as_preview_entry(
    authenticated_client: AsyncClient,
) -> None:
    """首个顶层路由是分组时，整项目预览应允许使用分组父路径作为 Runtime 重定向入口。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "分组入口预览工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "分组入口预览项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-group-route'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>chapter-one-page</div></template>",
            "file_type": "vue",
            "title": "第一章页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "group",
                    "route": "ch1",
                    "order": 0,
                    "group_title": "第一章",
                    "children": [
                        {
                            "route": "intro",
                            "order": 0,
                            "page_id": page["id"],
                        }
                    ],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    default_preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={},
    )
    assert default_preview_response.status_code == 200
    assert default_preview_response.json()["entry_descriptor"] == {
        "entry_type": "route",
        "route": "/ch1",
    }

    explicit_preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/ch1"}},
    )
    assert explicit_preview_response.status_code == 200
    assert explicit_preview_response.json()["entry_descriptor"] == {
        "entry_type": "route",
        "route": "/ch1",
    }


async def test_project_preview_artifact_should_reject_unknown_entry_route(
    authenticated_client: AsyncClient,
) -> None:
    """整项目预览显式指定不存在的路由时，应在后端直接拒绝请求。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "非法预览路由工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "非法预览路由项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    slider_upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("slider.svg", b"<svg><path d='slider-invalid-route'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert slider_upload_response.status_code == 200

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-page</div></template>",
            "file_type": "vue",
            "title": "路由页",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_response.json()["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/missing"}},
    )
    assert preview_response.status_code == 400
    assert preview_response.json()["code"] == "PREVIEW_ENTRY_ROUTE_NOT_FOUND"
