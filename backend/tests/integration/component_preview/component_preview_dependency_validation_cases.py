"""文件功能：承载组件预览 dependency validation 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.component_preview.component_preview_cases import *  # noqa: F403


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
