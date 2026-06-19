"""文件功能：承载组件预览 publish 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.component_preview.component_preview_cases import *  # noqa: F403


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
