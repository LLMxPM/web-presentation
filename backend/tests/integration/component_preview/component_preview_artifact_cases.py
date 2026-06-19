"""文件功能：承载组件预览 artifact 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.component_preview.component_preview_cases import *  # noqa: F403


async def test_page_module_dependencies_should_include_component_versions_and_runtime_public_modules(
    authenticated_client: AsyncClient,
) -> None:
    """页面当前源码依赖接口应返回固定组件版本和 Runtime 公共本地模块。"""

    workspace_id = await create_workspace(authenticated_client, "页面依赖工作空间")
    project_id = await create_project(authenticated_client, workspace_id, "页面依赖项目")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "页面卡片",
            "import_name": "PageCard",
            "content": "<template><div>card</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component_data = component_response.json()
    component_data = await publish_component(authenticated_client, component_data["id"])

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template>
  <RemoteCard />
  <AssetImage asset-name=\"logo\" />
</template>
<script setup lang=\"ts\">
import RemoteCard from '@workspace-components/{component_data['code']}/v/1'
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import {{ resolveResourcePath }} from '@runtime-kit/public/utils/assets.v1'
const url = resolveResourcePath('app')
</script>
            """.strip(),
            "file_type": "vue",
            "title": "模块依赖页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_id = page_response.json()["id"]

    dependency_response = await authenticated_client.get(f"/api/pages/{page_id}/module-dependencies")
    assert dependency_response.status_code == 200
    dependency_data = dependency_response.json()
    assert {(
        item["dependency_kind"],
        item.get("component_code"),
        item.get("component_version_no"),
        item.get("runtime_module_path"),
    ) for item in dependency_data["dependencies"]} == {
        ("workspace_component", component_data["code"], 1, None),
        ("runtime_local", None, None, "@runtime-kit/public/components/assets/AssetImage.v1.vue"),
        ("runtime_local", None, None, "@runtime-kit/public/utils/assets.v1"),
    }
    runtime_dependencies = {
        item["runtime_kit_base_name"]: item
        for item in dependency_data["dependencies"]
        if item["dependency_kind"] == "runtime_local"
    }
    assert runtime_dependencies["AssetImage"]["runtime_kit_name"] == "AssetImage.v1"
    assert runtime_dependencies["resolveResourcePath"]["runtime_kit_version_no"] == 1

async def test_project_preview_artifact_should_publish_component_modules_and_module_resolver_config(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """项目预览 artifact 应把路由页面引用的组件版本一起发布，并下发模块解析边界配置。"""

    workspace_id = await create_workspace(authenticated_client, "预览组件工作空间")
    project_id = await create_project(authenticated_client, workspace_id, "预览组件项目")
    await upload_icon_asset(authenticated_client, workspace_id, file_name="slider")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "预览按钮",
            "import_name": "PreviewButton",
            "content": """
<template>
  <button class=\"primary\">Preview Button</button>
</template>
<script setup lang=\"ts\">
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
</script>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component_data = component_response.json()
    component_data = await publish_component(authenticated_client, component_data["id"])

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template>
  <div><PreviewButton /></div>
</template>
<script setup lang=\"ts\">
import PreviewButton from '@workspace-components/{component_data['code']}/v/1'
import {{ resolveResourcePath }} from '@runtime-kit/public/utils/assets.v1'
const configUrl = resolveResourcePath('app')
</script>
            """.strip(),
            "file_type": "vue",
            "title": "预览组件页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_data = page_response.json()

    update_project_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_data["id"],
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

    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert set(manifest["modules"].keys()) == {
        f"src/views/{page_data['code']}.vue",
        f"src/workspace-components/{component_data['code']}/v/1.vue",
    }

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()
    module_resolver = config_bundle["module_resolver"]
    assert module_resolver["remote_component_prefix"] == "@workspace-components/"
    assert module_resolver["runtime_kit_alias"] == "@runtime-kit"
    assert module_resolver["runtime_kit_manifest_version"] == "1.0.0"
    assert {
        item["import_path"]
        for item in module_resolver["runtime_kit_exports"]
    } >= {
        "@runtime-kit/public/components/assets/AssetImage.v1.vue",
        "@runtime-kit/public/components/primitives/Icon.v1.vue",
        "@runtime-kit/public/utils/assets.v1",
    }

    component_module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": f"src/workspace-components/{component_data['code']}/v/1.vue"},
        headers=runtime_service_headers,
    )
    assert component_module_response.status_code == 200
    assert "Preview Button" in component_module_response.text

async def test_project_preview_artifact_should_include_relative_page_modules_in_snapshot(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """项目预览 artifact 应递归收录页面相对导入引用的其他页面模块。"""

    workspace_id = await create_workspace(authenticated_client, "页面递归依赖工作空间")
    project_id = await create_project(authenticated_client, workspace_id, "页面递归依赖项目")
    await upload_icon_asset(authenticated_client, workspace_id, file_name="slider")

    child_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div class=\"child-page\">child page content</div></template>",
            "file_type": "vue",
            "title": "子页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert child_page_response.status_code == 200
    child_page = child_page_response.json()

    parent_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template>
  <section><NestedChildPage /></section>
</template>
<script setup lang="ts">
import NestedChildPage from './{child_page["code"]}.vue'
</script>
            """.strip(),
            "file_type": "vue",
            "title": "父页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert parent_page_response.status_code == 200
    parent_page = parent_page_response.json()

    update_project_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": parent_page["id"],
                }
            ]
        },
    )
    assert update_project_response.status_code == 200

    dependency_response = await authenticated_client.get(
        f"/api/pages/{parent_page['id']}/module-dependencies"
    )
    assert dependency_response.status_code == 200
    assert {
        (
            item["dependency_kind"],
            item.get("component_code"),
            item.get("component_version_no"),
            item.get("runtime_module_path"),
        )
        for item in dependency_response.json()["dependencies"]
    } == {
        ("page_module", None, None, f"src/views/{child_page['code']}.vue"),
    }

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
    assert set(manifest["modules"].keys()) == {
        f"src/views/{parent_page['code']}.vue",
        f"src/views/{child_page['code']}.vue",
    }

    child_module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": f"src/views/{child_page['code']}.vue"},
        headers=runtime_service_headers,
    )
    assert child_module_response.status_code == 200
    assert "child page content" in child_module_response.text

async def test_standalone_page_preview_should_keep_entry_page_out_of_manifest_whitelist(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """单页面预览入口页应只写入 release_modules，不强制进入 manifest.modules 白名单。"""

    workspace_id = await create_workspace(authenticated_client, "单页预览工作空间")
    project_id = await create_project(authenticated_client, workspace_id, "单页预览项目")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "单页预览卡片",
            "import_name": "StandalonePreviewCard",
            "content": "<template><div>standalone component</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component_data = component_response.json()
    component_data = await publish_component(authenticated_client, component_data["id"])

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template>
  <StandaloneCard />
</template>
<script setup lang=\"ts\">
import StandaloneCard from '@workspace-components/{component_data['code']}/v/1'
</script>
            """.strip(),
            "file_type": "vue",
            "title": "单页预览页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_data = page_response.json()

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "module", "module_path": f"src/views/{page_data['code']}.vue"}},
    )
    assert preview_response.status_code == 200
    artifact_id = preview_response.json()["artifact_id"]

    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert set(manifest["modules"].keys()) == {
        f"src/workspace-components/{component_data['code']}/v/1.vue",
    }

    page_module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": f"src/views/{page_data['code']}.vue"},
        headers=runtime_service_headers,
    )
    assert page_module_response.status_code == 200
    assert "StandaloneCard" in page_module_response.text

async def test_component_draft_preview_should_publish_component_sandbox_config_bundle(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """组件草稿预览应生成纯沙箱配置，并通过本地组件预览入口加载目标组件。"""

    workspace_id = await create_workspace(authenticated_client, "组件宿主页工作空间")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "宿主页测试组件",
            "import_name": "HostPageTestComponent",
            "content": """
<template>
  <section class=\"preview-card\">{{ title }}</section>
</template>
<script setup lang=\"ts\">
defineProps<{ title?: string }>()
</script>
            """.strip(),
            "preview_schema": """
{
  "props": {
    "height": {
      "type": "number",
      "default": 320
    },
    "title": {
      "type": "string",
      "default": "Hello Preview"
    }
  }
}
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component_data = component_response.json()
    component_data = await publish_component(authenticated_client, component_data["id"])

    preview_response = await authenticated_client.post(
        f"/api/components/{component_data['id']}/preview-artifacts",
    )
    assert preview_response.status_code == 200
    preview_data = preview_response.json()
    assert preview_data["preview_kind"] == "component"
    assert preview_data["entry_descriptor"] == {"entry_type": "component_host"}
    assert "project_id" not in preview_data or preview_data["project_id"] is None

    artifact_id = preview_data["artifact_id"]
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["preview_kind"] == "component"
    assert manifest["entry_descriptor"] == {"entry_type": "component_host"}
    assert set(manifest["modules"].keys()) == {
        f"src/workspace-components/{component_data['code']}/v/1.vue",
    }

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()
    assert config_bundle["routes"] == {"routes": []}
    assert config_bundle["component_preview"] == {
        "component_import_path": f"@workspace-components/{component_data['code']}/v/1",
        "component_source": "workspace_component",
        "component_code": component_data["code"],
        "component_version_no": 1,
        "display_name": "宿主页测试组件",
            "schema": {
                "props": {
                    "height": {
                        "type": "number",
                        "default": 320,
                    },
                    "title": {
                        "type": "string",
                        "default": "Hello Preview",
                }
            }
        },
        "placement": {
            "width_mode": "percent",
            "width_value": 100,
            "height_mode": "auto",
            "height_value": None,
            "horizontal_align": "center",
            "vertical_align": "center",
            "padding": 48,
        },
    }

async def test_saved_component_preview_should_use_default_preview_options(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """已保存组件预览应使用默认页面尺寸、默认主题与默认组件占位。"""

    workspace_id = await create_workspace(authenticated_client, "保存态默认选项工作空间")
    icon_asset = await upload_icon_asset(authenticated_client, workspace_id, file_name="icon-home")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "默认配置组件",
            "import_name": "DefaultConfigComponent",
            "content": "<template><section><Icon name=\"icon-home\" />saved preview</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component_data = await publish_component(authenticated_client, component_response.json()["id"])
    component_id = int(component_data["id"])

    preview_response = await authenticated_client.post(f"/api/components/{component_id}/preview-artifacts")
    assert preview_response.status_code == 200
    assert preview_response.json()["viewport_width"] == 1920
    assert preview_response.json()["viewport_height"] == 1080

    artifact_id = preview_response.json()["artifact_id"]
    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()
    assert config_bundle["component_preview"]["placement"] == {
        "width_mode": "percent",
        "width_value": 100,
        "height_mode": "auto",
        "height_value": None,
        "horizontal_align": "center",
        "vertical_align": "center",
        "padding": 48,
    }
    assert config_bundle["app"]["app"]["page"] == {
        "width": 1920,
        "height": 1080,
        "baseFontSize": "20px",
        "iconDefaultStrokeWidth": 2,
    }
    assert config_bundle["icons"] == {
        "static_icons": [
            {
                "name": "icon-home",
                "src": "icon-home",
                "analysis": icon_asset["analysis_metadata"],
            }
        ]
    }
    assert "lightblue" in config_bundle["themes"]["themes"]

async def test_saved_component_preview_should_include_icons_from_transitive_component_dependencies(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """组件预览应递归扫描模块图，把间接依赖组件中的静态图标一并下发。"""

    workspace_id = await create_workspace(authenticated_client, "组件递归图标工作空间")
    icon_asset = await upload_icon_asset(authenticated_client, workspace_id, file_name="icon-leaf")

    leaf_component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "叶子图标组件",
            "import_name": "LeafIconComponent",
            "content": '<template><section><Icon name="icon-leaf" /></section></template>',
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert leaf_component_response.status_code == 200
    leaf_component = leaf_component_response.json()
    leaf_component = await publish_component(authenticated_client, leaf_component["id"])

    wrapper_component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "包装组件",
            "import_name": "WrapperComponent",
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
    wrapper_component = await publish_component(authenticated_client, wrapper_component["id"])

    preview_response = await authenticated_client.post(
        f"/api/components/{wrapper_component['id']}/preview-artifacts",
    )
    assert preview_response.status_code == 200

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{preview_response.json()['artifact_id']}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    assert config_bundle_response.json()["icons"] == {
        "static_icons": [
            {
                "name": "icon-leaf",
                "src": "icon-leaf",
                "analysis": icon_asset["analysis_metadata"],
            }
        ]
    }

async def test_component_draft_preview_should_create_hidden_system_project(
    authenticated_client: AsyncClient,
) -> None:
    """组件预览沙箱项目应自动创建，但不能出现在普通项目列表中。"""

    workspace_id = await create_workspace(authenticated_client, "系统项目隔离工作空间")

    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "系统项目测试组件",
            "import_name": "SystemProjectTestComponent",
            "content": "<template><div>system project preview</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component_data = await publish_component(authenticated_client, component_response.json()["id"])
    component_id = int(component_data["id"])

    preview_response = await authenticated_client.post(f"/api/components/{component_id}/preview-artifacts")
    assert preview_response.status_code == 200

    project_list_response = await authenticated_client.get(
        "/api/projects",
        params={"page": 1, "page_size": 100, "workspace_id": workspace_id},
    )
    assert project_list_response.status_code == 200
    assert project_list_response.json()["items"] == []

async def test_component_source_draft_preview_should_render_unsaved_source_without_persisting_version(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """未保存源码预览应基于内存内容生成临时 release，而不要求先保存组件版本。"""

    workspace_id = await create_workspace(authenticated_client, "源码草稿预览工作空间")

    dependency_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "被引用组件",
            "import_name": "ReferencedComponent",
            "content": "<template><div>dependency</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert dependency_response.status_code == 200
    dependency_data = dependency_response.json()
    dependency_data = await publish_component(authenticated_client, dependency_data["id"])

    preview_response = await authenticated_client.post(
        "/api/components/preview-artifacts/from-source",
        json={
            "workspace_id": workspace_id,
            "component_name": "未保存草稿组件",
            "content": f"""
<template>
  <section class=\"draft-card\"><RemoteDep />未保存草稿</section>
</template>
<script setup lang=\"ts\">
import RemoteDep from '@workspace-components/{dependency_data['code']}/v/1'
</script>
            """.strip(),
            "preview_schema": """
{
  "props": {
    "title": {
      "type": "string",
      "default": "Draft Preview"
    }
  }
}
            """.strip(),
            "file_type": "vue",
        },
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    artifact_id = preview_payload["artifact_id"]
    assert preview_payload["workspace_id"] == workspace_id
    assert "project_id" not in preview_payload or preview_payload["project_id"] is None

    config_bundle_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/config-bundle",
        headers=runtime_service_headers,
    )
    assert config_bundle_response.status_code == 200
    config_bundle = config_bundle_response.json()
    component_preview = config_bundle["component_preview"]
    assert component_preview["display_name"] == "未保存草稿组件"
    assert component_preview["component_version_no"] == 0
    assert component_preview["schema"] == {
        "props": {
            "title": {
                "type": "string",
                "default": "Draft Preview",
            }
        }
    }

    draft_module_path = f"src/workspace-components/{component_preview['component_code']}/v/0.vue"
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    assert set(manifest_response.json()["modules"].keys()) == {
        draft_module_path,
        f"src/workspace-components/{dependency_data['code']}/v/1.vue",
    }

    draft_module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": draft_module_path},
        headers=runtime_service_headers,
    )
    assert draft_module_response.status_code == 200
    assert "未保存草稿" in draft_module_response.text

async def test_component_source_draft_preview_should_apply_preview_options(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """未保存源码预览应允许覆盖页面、主题与占位配置，并按组件源码注入最小图标集合。"""

    workspace_id = await create_workspace(authenticated_client, "源码草稿配置覆盖工作空间")
    icon_asset = await upload_icon_asset(authenticated_client, workspace_id, file_name="icon-home")

    preview_response = await authenticated_client.post(
        "/api/components/preview-artifacts/from-source",
        json={
            "workspace_id": workspace_id,
            "component_name": "配置覆盖组件",
            "content": "<template><section><Icon name=\"icon-home\" />custom config preview</section></template>",
            "file_type": "vue",
            "preview_options": {
                "page": {
                    "width": 1280,
                    "height": 720,
                    "base_font_size": "18px",
                    "icon_default_stroke_width": 3,
                    "theme_config_yaml": """
themes:
  light:
    colorPrimary: "#111111"
                    """.strip(),
                },
                "placement": {
                    "width_mode": "fixed",
                    "width_value": 640,
                    "height_mode": "percent",
                    "height_value": 50,
                    "horizontal_align": "center",
                    "vertical_align": "end",
                    "padding": 16,
                },
            },
        },
    )
    assert preview_response.status_code == 200
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
    assert config_bundle["icons"] == {
        "static_icons": [
            {
                "name": "icon-home",
                "src": "icon-home",
                "analysis": icon_asset["analysis_metadata"],
            }
        ]
    }
    assert config_bundle["themes"] == {
        "themes": {
            "light": {
                "colorPrimary": "#111111",
            }
        }
    }
    assert config_bundle["component_preview"]["placement"] == {
        "width_mode": "fixed",
        "width_value": 640,
        "height_mode": "percent",
        "height_value": 50,
        "horizontal_align": "center",
        "vertical_align": "end",
        "padding": 16,
    }
    assert preview_response.json()["viewport_width"] == 1280
    assert preview_response.json()["viewport_height"] == 720
