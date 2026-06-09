"""文件功能：验证工作空间组件版本管理、源码依赖索引与预览模块图发布行为。"""

from httpx import AsyncClient

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


async def create_workspace(authenticated_client: AsyncClient, name: str = "组件工作空间") -> int:
    """创建一个启用中的工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def create_project(authenticated_client: AsyncClient, workspace_id: int, name: str = "组件项目") -> int:
    """创建一个启用中的项目并返回主键。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def upload_icon_asset(
    authenticated_client: AsyncClient,
    workspace_id: int,
    *,
    file_name: str,
) -> dict[str, object]:
    """向工作空间上传一个 SVG 图标资产，供预览配置校验使用。"""

    upload_file_name = file_name if file_name.endswith(".svg") else f"{file_name}.svg"
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (upload_file_name, f"<svg><path d='{file_name}'/></svg>".encode("utf-8"), "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]", "name": file_name},
    )
    assert response.status_code == 200
    return response.json()


async def publish_component(
    authenticated_client: AsyncClient,
    component_id: int,
    *,
    release_name: str | None = None,
    change_note: str | None = "发布测试版本",
) -> dict[str, object]:
    """发布组件草稿并返回最新组件响应。"""

    response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": release_name, "change_note": change_note},
    )
    assert response.status_code == 200
    return response.json()


async def test_component_publish_should_build_versions_and_current_dependencies(
    authenticated_client: AsyncClient,
) -> None:
    """组件草稿发布后应保存正式版本历史，并暴露当前发布版依赖索引。"""

    workspace_id = await create_workspace(authenticated_client, "组件依赖工作空间")

    base_component = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "基础按钮",
            "import_name": "BaseButton",
            "content": "<template><button>Base</button></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert base_component.status_code == 200
    base_component_data = base_component.json()
    assert base_component_data["current_version_no"] == 0
    assert base_component_data["has_unpublished_changes"] is True
    base_component_data = await publish_component(authenticated_client, base_component_data["id"])
    assert base_component_data["current_version_no"] == 1
    assert base_component_data["has_unpublished_changes"] is False

    wrapper_component = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "按钮包装器",
            "import_name": "ButtonWrapper",
            "content": f"""
<template>
  <div class=\"wrapper\"><BaseButton /></div>
</template>
<script setup lang=\"ts\">
import BaseButton from '@workspace-components/{base_component_data['code']}/v/1'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
</script>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert wrapper_component.status_code == 200
    wrapper_component_data = wrapper_component.json()
    assert wrapper_component_data["code"].startswith("CMP")
    assert wrapper_component_data["current_version_no"] == 0
    assert wrapper_component_data["has_unpublished_changes"] is True
    wrapper_component_data = await publish_component(authenticated_client, wrapper_component_data["id"])
    assert wrapper_component_data["current_version_no"] == 1

    dependency_response = await authenticated_client.get(
        f"/api/components/{wrapper_component_data['id']}/current-dependencies"
    )
    assert dependency_response.status_code == 200
    dependency_data = dependency_response.json()
    assert dependency_data["current_version_no"] == 1
    assert {(
        item["dependency_kind"],
        item.get("component_code"),
        item.get("component_version_no"),
        item.get("runtime_module_path"),
    ) for item in dependency_data["dependencies"]} == {
        ("workspace_component", base_component_data["code"], 1, None),
        ("runtime_local", None, None, "@runtime-kit/public/components/primitives/Icon.v1.vue"),
    }
    icon_dependency = next(item for item in dependency_data["dependencies"] if item.get("runtime_kit_base_name") == "Icon")
    assert icon_dependency["runtime_kit_name"] == "Icon.v1"
    assert icon_dependency["runtime_kit_version_no"] == 1
    assert icon_dependency["runtime_kit_import_path"] == "@runtime-kit/public/components/primitives/Icon.v1.vue"
    await upload_icon_asset(authenticated_client, workspace_id, file_name="app")

    update_response = await authenticated_client.patch(
        f"/api/components/{wrapper_component_data['id']}",
        json={
            "content": f"""
<template>
  <section><BaseButton /></section>
</template>
<script setup lang=\"ts\">
import BaseButton from '@workspace-components/{base_component_data['code']}/v/1'
import {{ resolveResourcePath }} from '@runtime-kit/public/utils/assets.v1'
const previewConfigUrl = resolveResourcePath('app')
</script>
            """.strip(),
            "change_note": "切换到 core 公共模块引用",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 1
    assert update_response.json()["has_unpublished_changes"] is True

    publish_response = await publish_component(authenticated_client, wrapper_component_data["id"])
    assert publish_response["current_version_no"] == 2
    assert publish_response["has_unpublished_changes"] is False

    versions_response = await authenticated_client.get(
        f"/api/components/{wrapper_component_data['id']}/versions"
    )
    assert versions_response.status_code == 200
    version_list = versions_response.json()
    assert [item["version_no"] for item in version_list] == [2, 1]


async def test_component_draft_save_publish_restore_and_version_preview(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """组件草稿可反复保存，发布才生成版本；发布版可预览并可恢复到草稿。"""

    workspace_id = await create_workspace(authenticated_client, "草稿发布工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "草稿组件",
            "import_name": "DraftComponent",
            "content": "<template><div>draft v1</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    assert component["current_version_no"] == 0
    assert component["draft_base_version_no"] == 0
    assert component["has_unpublished_changes"] is True

    versions_response = await authenticated_client.get(f"/api/components/{component['id']}/versions")
    assert versions_response.status_code == 200
    assert versions_response.json() == []

    publish_v1_response = await authenticated_client.post(
        f"/api/components/{component['id']}/publish",
        json={"release_name": "首个发布版", "change_note": "首次定版"},
    )
    assert publish_v1_response.status_code == 200
    published_v1 = publish_v1_response.json()
    assert published_v1["current_version_no"] == 1
    assert published_v1["draft_base_version_no"] == 1
    assert published_v1["has_unpublished_changes"] is False

    update_response = await authenticated_client.patch(
        f"/api/components/{component['id']}",
        json={"content": "<template><div>draft v2</div></template>", "change_note": "临时保存"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 1
    assert update_response.json()["has_unpublished_changes"] is True

    versions_after_draft = await authenticated_client.get(f"/api/components/{component['id']}/versions")
    assert versions_after_draft.status_code == 200
    assert [item["version_no"] for item in versions_after_draft.json()] == [1]

    publish_v2 = await publish_component(authenticated_client, component["id"], release_name="第二版")
    assert publish_v2["current_version_no"] == 2
    assert publish_v2["has_unpublished_changes"] is False

    preview_v1_response = await authenticated_client.post(
        f"/api/components/{component['id']}/versions/1/preview-artifact",
    )
    assert preview_v1_response.status_code == 200
    artifact_id = preview_v1_response.json()["artifact_id"]
    module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        params={"path": f"src/workspace-components/{component['code']}/v/1.vue"},
        headers=runtime_service_headers,
    )
    assert module_response.status_code == 200
    assert "draft v1" in module_response.text
    assert "draft v2" not in module_response.text

    restore_response = await authenticated_client.post(
        f"/api/components/{component['id']}/versions/1/restore-to-draft",
        json={"change_note": "恢复首版草稿"},
    )
    assert restore_response.status_code == 200
    restored = restore_response.json()
    assert restored["current_version_no"] == 2
    assert restored["draft_base_version_no"] == 1
    assert restored["has_unpublished_changes"] is True
    assert restored["content"] == "<template><div>draft v1</div></template>"

    versions_after_restore = await authenticated_client.get(f"/api/components/{component['id']}/versions")
    assert versions_after_restore.status_code == 200
    assert [item["version_no"] for item in versions_after_restore.json()] == [2, 1]


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


async def test_component_references_should_query_and_upgrade_direct_page_and_component_refs(
    authenticated_client: AsyncClient,
) -> None:
    """组件引用接口应分开展示页面/组件直接引用，并支持升级到当前发布版本。"""

    workspace_id = await create_workspace(authenticated_client, "组件引用升级工作空间")
    project_id = await create_project(authenticated_client, workspace_id, "组件引用升级项目")

    target_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "目标组件",
            "import_name": "TargetCard",
            "content": "<template><article>v1</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert target_response.status_code == 200
    target_component = await publish_component(authenticated_client, target_response.json()["id"])

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template><TargetCard /></template>
<script setup lang=\"ts\">
import TargetCard from '@workspace-components/{target_component['code']}/v/1.vue'
</script>
            """.strip(),
            "file_type": "vue",
            "title": "引用目标组件页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_id = page_response.json()["id"]

    archived_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template><TargetCard /></template>
<script setup lang=\"ts\">
import TargetCard from '@workspace-components/{target_component['code']}/v/1'
</script>
            """.strip(),
            "file_type": "vue",
            "title": "归档引用页面",
            "status": "archived",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert archived_page_response.status_code == 200

    archived_project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "归档引用项目", "status": "archived"},
    )
    assert archived_project_response.status_code == 200
    archived_project_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": f"""
<template><TargetCard /></template>
<script setup lang=\"ts\">
import TargetCard from '@workspace-components/{target_component['code']}/v/1'
</script>
            """.strip(),
            "file_type": "vue",
            "title": "归档项目引用页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": archived_project_response.json()["id"],
        },
    )
    assert archived_project_page_response.status_code == 200

    wrapper_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "引用方组件",
            "import_name": "WrapperCard",
            "content": f"""
<template><TargetCard /></template>
<script setup lang=\"ts\">
import TargetCard from '@workspace-components/{target_component['code']}/v/1'
</script>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert wrapper_response.status_code == 200
    wrapper_component = await publish_component(authenticated_client, wrapper_response.json()["id"])

    archived_wrapper_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "归档引用方组件",
            "import_name": "ArchivedWrapperCard",
            "content": f"""
<template><TargetCard /></template>
<script setup lang=\"ts\">
import TargetCard from '@workspace-components/{target_component['code']}/v/1'
</script>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert archived_wrapper_response.status_code == 200
    archived_wrapper = await publish_component(authenticated_client, archived_wrapper_response.json()["id"])
    archive_wrapper_update = await authenticated_client.patch(
        f"/api/components/{archived_wrapper['id']}",
        json={"status": "archived"},
    )
    assert archive_wrapper_update.status_code == 200

    update_target_response = await authenticated_client.patch(
        f"/api/components/{target_component['id']}",
        json={
            "content": "<template><article>v2</article></template>",
            "change_note": "准备发布 v2",
        },
    )
    assert update_target_response.status_code == 200
    target_component = await publish_component(authenticated_client, target_component["id"], release_name="v2")
    assert target_component["current_version_no"] == 2

    references_response = await authenticated_client.get(f"/api/components/{target_component['id']}/references")
    assert references_response.status_code == 200
    references = references_response.json()
    assert references["current_version_no"] == 2
    assert {item["page_title"] for item in references["page_references"]} == {"引用目标组件页面"}
    assert {item["component_name"] for item in references["component_references"]} == {"引用方组件"}
    assert references["page_references"] == [
        {
            "page_id": page_id,
            "page_code": page_response.json()["code"],
            "page_title": "引用目标组件页面",
            "project_id": project_id,
            "project_name": "组件引用升级项目",
            "current_version_no": 1,
            "page_version_id": references["page_references"][0]["page_version_id"],
            "referenced_component_version_no": 1,
            "is_current_version": False,
            "can_upgrade": True,
        }
    ]
    component_reference = references["component_references"][0]
    assert component_reference["component_id"] == wrapper_component["id"]
    assert component_reference["referenced_component_version_no"] == 1
    assert component_reference["draft_referenced_component_version_no"] == 1
    assert component_reference["can_upgrade"] is True

    upgrade_response = await authenticated_client.post(
        f"/api/components/{target_component['id']}/references/upgrade",
        json={"page_ids": [page_id], "component_ids": [wrapper_component["id"]]},
    )
    assert upgrade_response.status_code == 200
    upgrade_data = upgrade_response.json()
    assert upgrade_data["updated_pages"][0]["page_id"] == page_id
    assert upgrade_data["updated_pages"][0]["previous_version_no"] == 1
    assert upgrade_data["updated_pages"][0]["current_version_no"] == 2
    assert upgrade_data["updated_components"][0]["component_id"] == wrapper_component["id"]
    assert upgrade_data["updated_components"][0]["current_version_no"] == 1
    assert upgrade_data["failures"] == []

    upgraded_page_response = await authenticated_client.get(f"/api/pages/{page_id}")
    assert upgraded_page_response.status_code == 200
    upgraded_page = upgraded_page_response.json()
    assert upgraded_page["current_version_no"] == 2
    assert f"@workspace-components/{target_component['code']}/v/2.vue" in upgraded_page["page_content"]

    page_dependency_response = await authenticated_client.get(f"/api/pages/{page_id}/module-dependencies")
    assert page_dependency_response.status_code == 200
    assert [
        item["component_version_no"]
        for item in page_dependency_response.json()["dependencies"]
        if item["dependency_kind"] == "workspace_component"
    ] == [2]

    upgraded_wrapper_response = await authenticated_client.get(f"/api/components/{wrapper_component['id']}")
    assert upgraded_wrapper_response.status_code == 200
    upgraded_wrapper = upgraded_wrapper_response.json()
    assert upgraded_wrapper["current_version_no"] == 1
    assert upgraded_wrapper["has_unpublished_changes"] is True
    assert f"@workspace-components/{target_component['code']}/v/2" in upgraded_wrapper["content"]

    second_references_response = await authenticated_client.get(f"/api/components/{target_component['id']}/references")
    assert second_references_response.status_code == 200
    second_references = second_references_response.json()
    assert second_references["page_references"][0]["is_current_version"] is True
    assert second_references["page_references"][0]["can_upgrade"] is False
    assert second_references["component_references"][0]["is_current_version"] is False
    assert second_references["component_references"][0]["draft_is_current_version"] is True
    assert second_references["component_references"][0]["can_upgrade"] is False

    second_upgrade_response = await authenticated_client.post(
        f"/api/components/{target_component['id']}/references/upgrade",
        json={"page_ids": [page_id], "component_ids": [wrapper_component["id"]]},
    )
    assert second_upgrade_response.status_code == 200
    skipped_codes = {item["code"] for item in second_upgrade_response.json()["skipped"]}
    assert {"ALREADY_CURRENT", "SOURCE_NOT_CHANGED"}.issubset(skipped_codes)


async def test_remote_module_save_should_reject_invalid_component_alias_and_forbidden_runtime_local_import(
    authenticated_client: AsyncClient,
) -> None:
    """页面和组件保存时应拒绝非法组件别名及未开放的 Runtime 本地模块。"""

    workspace_id = await create_workspace(authenticated_client, "非法依赖工作空间")

    invalid_component_alias_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "非法别名组件",
            "import_name": "InvalidAliasComponent",
            "content": """
<script setup lang=\"ts\">
import DemoCard from '@workspace-components/CMP_BAD'
</script>
<template><DemoCard /></template>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert invalid_component_alias_response.status_code == 400
    assert invalid_component_alias_response.json()["code"] == "REMOTE_COMPONENT_IMPORT_INVALID"

    forbidden_runtime_import_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "非法本地模块组件",
            "import_name": "InvalidLocalModuleComponent",
            "content": """
<script setup lang=\"ts\">
import AppIcon from '@/components/common/AppIcon.vue'
</script>
<template><AppIcon /></template>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert forbidden_runtime_import_response.status_code == 400
    assert forbidden_runtime_import_response.json()["code"] == "RUNTIME_LOCAL_IMPORT_FORBIDDEN"

    unversioned_runtime_import_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "未版本化 Runtime Kit 组件",
            "import_name": "UnversionedRuntimeKitComponent",
            "content": """
<script setup lang=\"ts\">
import Icon from '@runtime-kit/public/components/primitives/Icon.vue'
</script>
<template><Icon name=\"home\" /></template>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert unversioned_runtime_import_response.status_code == 400
    assert unversioned_runtime_import_response.json()["code"] == "RUNTIME_LOCAL_IMPORT_FORBIDDEN"

    project_id = await create_project(authenticated_client, workspace_id, "非法页面依赖项目")
    forbidden_page_import_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "非法页面依赖",
            "page_content": """
<script setup lang=\"ts\">
import AppIcon from '@/components/common/AppIcon.vue'
</script>
<template><AppIcon /></template>
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert forbidden_page_import_response.status_code == 400
    assert forbidden_page_import_response.json()["code"] == "RUNTIME_LOCAL_IMPORT_FORBIDDEN"


async def test_component_save_should_reject_invalid_preview_schema_json(
    authenticated_client: AsyncClient,
) -> None:
    """组件保存时应拒绝非法 previewSchema JSON，避免脏数据进入预览链路。"""

    workspace_id = await create_workspace(authenticated_client, "预览 Schema 校验工作空间")

    invalid_schema_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "非法预览 Schema 组件",
            "import_name": "InvalidPreviewSchemaComponent",
            "content": "<template><div>invalid schema</div></template>",
            "preview_schema": "{ invalid json }",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert invalid_schema_response.status_code == 400
    assert invalid_schema_response.json()["code"] == "COMPONENT_PREVIEW_SCHEMA_INVALID"

    unversioned_schema_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "未版本化 Slot 组件",
            "import_name": "UnversionedSlotComponent",
            "content": "<template><section><slot /></section></template>",
            "preview_schema": """
{
  "props": {
    "height": {
      "type": "number",
      "default": 320
    }
  },
  "slots": {
    "default": {
      "default": [
        {
          "type": "component",
          "component": "@runtime-kit/public/components/primitives/Icon.vue"
        }
      ]
    }
  }
}
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert unversioned_schema_response.status_code == 400
    assert unversioned_schema_response.json()["code"] == "COMPONENT_PREVIEW_SCHEMA_INVALID"


async def test_component_preview_schema_should_validate_slot_component_runtime_paths(
    authenticated_client: AsyncClient,
) -> None:
    """previewSchema 的 slot.component 应复用 Runtime Kit manifest 校验。"""

    workspace_id = await create_workspace(authenticated_client, "预览 Slot 校验工作空间")

    valid_schema_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "合法 Slot 组件",
            "import_name": "ValidSlotComponent",
            "content": "<template><section><slot /></section></template>",
            "preview_schema": """
{
  "props": {
    "height": {
      "type": "number",
      "default": 320
    }
  },
  "slots": {
    "default": {
      "default": [
        {
          "type": "component",
          "component": "@runtime-kit/public/components/primitives/Icon.v1.vue",
          "props": {
            "name": "Home"
          }
        }
      ]
    }
  }
}
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert valid_schema_response.status_code == 200

    invalid_schema_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "非法 Slot 组件",
            "import_name": "InvalidSlotComponent",
            "content": "<template><section><slot /></section></template>",
            "preview_schema": """
{
  "slots": {
    "default": {
      "default": [
        {
          "type": "component",
          "component": "@/components/common/AppIcon.vue"
        }
      ]
    }
  }
}
            """.strip(),
            "file_type": "vue",
            "status": "active",
        },
    )
    assert invalid_schema_response.status_code == 400
    assert invalid_schema_response.json()["code"] == "COMPONENT_PREVIEW_SCHEMA_INVALID"


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


async def test_component_source_draft_preview_should_reject_transient_cycle(
    authenticated_client: AsyncClient,
) -> None:
    """未保存源码预览引入循环依赖时，应在生成 release 前被拒绝。"""

    workspace_id = await create_workspace(authenticated_client, "源码草稿循环工作空间")

    component_a_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "组件A",
            "import_name": "ComponentA",
            "content": "<template><div>A</div></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_a_response.status_code == 200
    component_a = component_a_response.json()
    component_a = await publish_component(authenticated_client, component_a["id"])

    component_b_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "组件B",
            "import_name": "ComponentB",
            "content": f"""
<template><ComponentA /></template>
<script setup lang=\"ts\">
import ComponentA from '@workspace-components/{component_a['code']}/v/1'
</script>
            """.strip(),
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_b_response.status_code == 200
    component_b = component_b_response.json()
    component_b = await publish_component(authenticated_client, component_b["id"])

    preview_response = await authenticated_client.post(
        "/api/components/preview-artifacts/from-source",
        json={
            "workspace_id": workspace_id,
            "component_id": component_a["id"],
            "component_name": component_a["name"],
            "content": f"""
<template><ComponentB /></template>
<script setup lang=\"ts\">
import ComponentB from '@workspace-components/{component_b['code']}/v/1'
</script>
            """.strip(),
            "file_type": "vue",
        },
    )
    assert preview_response.status_code == 400
    assert preview_response.json()["code"] == "COMPONENT_DEPENDENCY_CYCLE_DETECTED"
