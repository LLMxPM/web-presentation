"""文件功能：验证 icon 资产结构化分析元数据与按逻辑名下发的预览配置。"""

from httpx import AsyncClient

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str, theme_key: str | None = None) -> int:
    """创建测试项目并返回主键。"""

    payload = {
        "workspace_id": workspace_id,
        "name": name,
        "status": "active",
    }
    if theme_key is not None:
        payload["theme_key"] = theme_key
    response = await authenticated_client.post("/api/projects", json=payload)
    assert response.status_code == 200
    return response.json()["id"]


async def _upload_icon(
    authenticated_client: AsyncClient,
    workspace_id: int,
    *,
    file_name: str,
    content: bytes,
    content_type: str,
) -> dict[str, object]:
    """上传 icon 资产并返回响应体。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (file_name, content, content_type)},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert response.status_code == 200
    return response.json()


async def test_icon_asset_upload_should_generate_structured_analysis_metadata(
    authenticated_client: AsyncClient,
) -> None:
    """新上传 icon 资产应写入结构化分析元数据，而不是复用 tags。"""

    workspace_id = await _create_workspace(authenticated_client, "图标分析工作空间")

    stroke_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="stroke-icon.svg",
        content=b'<svg stroke="#111" fill="none"><path d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )
    assert stroke_icon["analysis_metadata"]["kind"] == "icon"
    assert stroke_icon["analysis_metadata"]["icon"]["render_mode"] == "inline_svg"
    assert stroke_icon["analysis_metadata"]["icon"]["style"] == "stroke"
    assert stroke_icon["analysis_metadata"]["icon"]["stroke_width_editable"] is True
    assert stroke_icon["analysis_metadata"]["icon"]["analysis_status"] == "analyzed"

    fill_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="fill-icon.svg",
        content=b'<svg><path fill="#111" d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )
    assert fill_icon["analysis_metadata"]["icon"]["style"] == "fill"
    assert fill_icon["analysis_metadata"]["icon"]["stroke_width_editable"] is False
    assert fill_icon["analysis_metadata"]["icon"]["analysis_status"] == "unsupported"

    complex_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="complex-icon.svg",
        content=b'<svg><filter id="f" /><path stroke="#111" d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )
    assert complex_icon["analysis_metadata"]["icon"]["style"] == "complex"
    assert complex_icon["analysis_metadata"]["icon"]["stroke_width_editable"] is False

    raster_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="photo-icon.png",
        content=b"fake-png",
        content_type="image/png",
    )
    assert raster_icon["analysis_metadata"]["icon"]["format"] == "image"
    assert raster_icon["analysis_metadata"]["icon"]["render_mode"] == "image"
    assert raster_icon["analysis_metadata"]["icon"]["stroke_width_editable"] is False


async def test_project_preview_icon_config_should_include_analysis_for_theme_project_icon(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """整项目预览下发的 static_icons 应携带主题项目图标的分析元数据。"""

    workspace_id = await _create_workspace(authenticated_client, "主题项目图标分析空间")
    project_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="theme-project-icon.svg",
        content=b'<svg stroke="#111" fill="none"><path d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )

    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "analysis-theme",
            "name": "分析主题",
            "description": "带项目图标分析",
            "project_icon_asset_id": project_icon["id"],
            "palette": {
                "text": {"primary": "#111111", "secondary": "#333333", "invert": "#ffffff"},
                "background": {"default": "#ffffff", "invert": "#111111"},
                "border": {"default": "#d1d5db", "subtle": "#e5e7eb"},
                "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
                "accent": ["#2563eb"],
            },
        },
    )
    assert theme_response.status_code == 200

    project_id = await _create_project(authenticated_client, workspace_id, "主题图标项目", theme_key="analysis-theme")
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><section>theme icon project</section></template>",
            "file_type": "vue",
            "title": "主题图标首页",
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
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    static_icons = config_bundle_response.json()["icons"]["static_icons"]
    assert static_icons == [
        {
            "name": "theme-project-icon",
            "src": "theme-project-icon",
            "analysis": project_icon["analysis_metadata"],
        }
    ]


async def test_project_preview_icon_config_should_include_icons_from_transitive_workspace_components(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """整项目预览应递归扫描已发布模块图，收录页面间接依赖组件里的静态图标。"""

    workspace_id = await _create_workspace(authenticated_client, "递归图标分析空间")
    nested_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="nested-icon.svg",
        content=b'<svg stroke="#111" fill="none"><path d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )
    project_id = await _create_project(authenticated_client, workspace_id, "递归图标项目")

    leaf_component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "叶子图标组件",
            "import_name": "LeafIconComponent",
            "content": '<template><section><Icon name="nested-icon" /></section></template>',
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert leaf_component_response.status_code == 200
    leaf_component = leaf_component_response.json()
    leaf_publish_response = await authenticated_client.post(
        f"/api/components/{leaf_component['id']}/publish",
        json={"change_note": "发布叶子组件"},
    )
    assert leaf_publish_response.status_code == 200
    leaf_component = leaf_publish_response.json()

    wrapper_component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "包装图标组件",
            "import_name": "WrapperIconComponent",
            "content": f"""
<template>
  <LeafIcon />
</template>
<script setup lang="ts">
import LeafIcon from '@workspace-components/{leaf_component["code"]}/v/1'
</script>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert wrapper_component_response.status_code == 200
    wrapper_component = wrapper_component_response.json()
    wrapper_publish_response = await authenticated_client.post(
        f"/api/components/{wrapper_component['id']}/publish",
        json={"change_note": "发布包装组件"},
    )
    assert wrapper_publish_response.status_code == 200
    wrapper_component = wrapper_publish_response.json()

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template>
  <WrapperIcon />
</template>
<script setup lang="ts">
import WrapperIcon from '@workspace-components/{wrapper_component["code"]}/v/1'
</script>
            """.strip(),
            "file_type": "vue",
            "title": "递归图标首页",
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
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{preview_response.json()['artifact_id']}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    assert config_bundle_response.json()["icons"]["static_icons"] == [
        {
            "name": "nested-icon",
            "src": "nested-icon",
            "analysis": nested_icon["analysis_metadata"],
        }
    ]


async def test_component_preview_should_backfill_legacy_icon_analysis_metadata(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """老 icon 资产缺少 analysis_metadata 时，组件预览应补齐分析信息并走内联 SVG。"""

    workspace_id = await _create_workspace(authenticated_client, "老图标兼容空间")
    legacy_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="legacy-icon.svg",
        content=b'<svg stroke="#111" fill="none"><path d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )

    async with get_session_factory()() as session:
        asset = await session.scalar(select(WorkspaceAsset).where(WorkspaceAsset.id == legacy_icon["id"]))
        assert asset is not None
        asset.analysis_metadata = None
        await session.commit()

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "老图标组件",
            "import_name": "LegacyIconComponent",
            "content": '<template><section><Icon name="legacy-icon" /></section></template>',
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    publish_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/publish",
        json={"change_note": "发布老图标组件"},
    )
    assert publish_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/preview-artifacts",
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    static_icons = config_bundle_response.json()["icons"]["static_icons"]
    assert static_icons == [
        {
            "name": "legacy-icon",
            "src": "legacy-icon",
            "analysis": {
                "schema_version": 1,
                "kind": "icon",
                "icon": {
                    "format": "svg",
                    "render_mode": "inline_svg",
                    "style": "stroke",
                    "inline_safe": True,
                    "stroke_width_editable": True,
                    "analysis_status": "analyzed",
                    "reasons": ["检测到纯描边 SVG，可安全应用描边宽度。"],
                },
            },
        }
    ]

    async with get_session_factory()() as session:
        asset = await session.scalar(select(WorkspaceAsset).where(WorkspaceAsset.id == legacy_icon["id"]))
        assert asset is not None
        assert asset.analysis_metadata == static_icons[0]["analysis"]


async def test_component_preview_should_collect_icon_names_from_static_array_v_for(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """组件预览应从顶层 const 数组对象字面量和 v-for 中收集 Icon 名称。"""

    workspace_id = await _create_workspace(authenticated_client, "数组图标预览空间")
    doc_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="doc-icon.svg",
        content=b'<svg stroke="#111" fill="none"><path d="M0 0 L10 10"/></svg>',
        content_type="image/svg+xml",
    )
    image_icon = await _upload_icon(
        authenticated_client,
        workspace_id,
        file_name="image-icon.svg",
        content=b'<svg stroke="#111" fill="none"><path d="M0 0 L8 8"/></svg>',
        content_type="image/svg+xml",
    )

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "数组图标组件",
            "import_name": "StaticArrayIconComponent",
            "content": """
<script setup lang="ts">
const items = [
  { icon: 'doc-icon', label: '文档' },
  { icon: 'image-icon', label: '图片' },
]
</script>

<template>
  <section>
    <Icon v-for="item in items" :key="item.icon" :name="item.icon" />
  </section>
</template>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    publish_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/publish",
        json={"change_note": "发布数组图标组件"},
    )
    assert publish_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/preview-artifacts",
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    assert config_bundle_response.json()["icons"]["static_icons"] == [
        {"name": "doc-icon", "src": "doc-icon", "analysis": doc_icon["analysis_metadata"]},
        {"name": "image-icon", "src": "image-icon", "analysis": image_icon["analysis_metadata"]},
    ]


async def test_component_preview_should_reject_dynamic_icon_name(
    authenticated_client: AsyncClient,
) -> None:
    """组件预览遇到无法静态解析的 Icon :name 时，应直接报错。"""

    workspace_id = await _create_workspace(authenticated_client, "动态图标报错空间")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "动态图标组件",
            "import_name": "DynamicIconComponent",
            "content": '<template><section><Icon :name="iconName" /></section></template>',
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    publish_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/publish",
        json={"change_note": "发布动态图标组件"},
    )
    assert publish_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/components/{component_response.json()['id']}/preview-artifacts",
    )
    assert preview_response.status_code == 400
    assert preview_response.json()["code"] == "PREVIEW_ICON_NAME_DYNAMIC_UNSUPPORTED"
    assert "顶层 const 数组对象字面量" in str(preview_response.json())
