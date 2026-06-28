"""文件功能：承载 catalog routes versioning 场景的拆分测试用例。"""

from __future__ import annotations

from tests.api.catalog.catalog_cases import *  # noqa: F403


async def test_page_save_should_build_component_index_for_each_version(authenticated_client: AsyncClient) -> None:
    """页面保存后应按版本记录组件集合与 Icon/Asset 的 name 参数集合。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件索引工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "组件索引项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    initial_code = """
<script setup lang="ts">
const resourceCards = [
  { icon: 'doc-icon', cover: 'cover-a' },
  { icon: 'image-icon', cover: 'cover-b' },
]
</script>

<template>
  <div>
    <Icon name="home" />
    <AssetImage name="cover-image" />
    <div v-for="item in resourceCards" :key="item.icon">
      <Icon :name="item.icon" />
      <AssetImage :name="item.cover" />
    </div>
    <AssetMermaid :name="'graph-a'" />
    <AssetDrawio :name="dynamicName" />
    <CustomPanel />
    <asset-image name="cover-image" />
  </div>
</template>
    """.strip()
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": initial_code,
            "file_type": "vue",
            "title": "组件索引页面",
            "status": "active",
            "project_id": project_id,
            "workspace_id": workspace_id,
        },
    )
    assert create_response.status_code == 200
    page_id = create_response.json()["id"]

    updated_code = """
<template>
  <section>
    <Icon name="settings" />
    <AssetImage :name="assetName" />
    <AnotherWidget />
  </section>
</template>
    """.strip()
    update_response = await authenticated_client.patch(
        f"/api/pages/{page_id}",
        json={"page_content": updated_code, "file_type": "vue"},
    )
    assert update_response.status_code == 200

    from app.db.session import get_session_factory
    from app.models.page_component_resource import PageVersionComponentResource
    from app.models.page_component_usage import PageVersionComponentUsage
    from app.models.page_version import PageVersion

    async with get_session_factory()() as session:
        version_rows = (
            await session.execute(
                select(PageVersion).where(PageVersion.page_id == page_id).order_by(PageVersion.version_no.asc())
            )
        ).scalars().all()
        assert [item.version_no for item in version_rows] == [1, 2]

        version_1_usages = (
            await session.execute(
                select(PageVersionComponentUsage.component_name, PageVersionComponentUsage.project_id).where(
                    PageVersionComponentUsage.page_version_id == version_rows[0].id
                )
            )
        ).all()
        assert {item.component_name for item in version_1_usages} == {
            "Icon",
            "AssetImage",
            "AssetMermaid",
            "AssetDrawio",
            "CustomPanel",
        }
        assert {item.project_id for item in version_1_usages} == {project_id}

        version_1_resources = (
            await session.execute(
                select(
                    PageVersionComponentResource.component_name,
                    PageVersionComponentResource.resource_name,
                    PageVersionComponentResource.project_id,
                ).where(PageVersionComponentResource.page_version_id == version_rows[0].id)
            )
        ).all()
        assert {(item.component_name, item.resource_name) for item in version_1_resources} == {
            ("Icon", "home"),
            ("Icon", "doc-icon"),
            ("Icon", "image-icon"),
            ("AssetImage", "cover-image"),
            ("AssetImage", "cover-a"),
            ("AssetImage", "cover-b"),
            ("AssetMermaid", "graph-a"),
            ("AssetDrawio", "__DYNAMIC__"),
        }
        assert {item.project_id for item in version_1_resources} == {project_id}

        version_2_usages = (
            await session.execute(
                select(PageVersionComponentUsage.component_name).where(
                    PageVersionComponentUsage.page_version_id == version_rows[1].id
                )
            )
        ).scalars().all()
        assert set(version_2_usages) == {"Icon", "AssetImage", "AnotherWidget"}

        version_2_resources = (
            await session.execute(
                select(
                    PageVersionComponentResource.component_name,
                    PageVersionComponentResource.resource_name,
                ).where(PageVersionComponentResource.page_version_id == version_rows[1].id)
            )
        ).all()
        assert {(item.component_name, item.resource_name) for item in version_2_resources} == {
            ("Icon", "settings"),
            ("AssetImage", "__DYNAMIC__"),
        }

async def test_get_page_current_component_index_should_return_latest_version_index(
    authenticated_client: AsyncClient,
) -> None:
    """页面组件索引接口应返回当前版本对应的组件与资源集合。"""

    workspace = await _create_catalog_workspace(authenticated_client, "组件索引独立空间")
    project = await _create_catalog_project(authenticated_client, workspace["id"], "组件索引独立项目")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": """
<template>
  <div>
    <Icon name="home" />
    <AssetImage name="cover" />
  </div>
</template>
            """.strip(),
            "file_type": "vue",
            "title": "组件索引接口页面",
            "status": "active",
            "workspace_id": workspace["id"],
            "project_id": project["id"],
        },
    )
    assert create_response.status_code == 200
    page_id = create_response.json()["id"]

    first_index_response = await authenticated_client.get(f"/api/pages/{page_id}/component-index")
    assert first_index_response.status_code == 200
    first_index_data = first_index_response.json()
    assert first_index_data["current_version_no"] == 1
    assert set(first_index_data["components"]) == {"Icon", "AssetImage"}
    assert {(item["component_name"], item["resource_name"]) for item in first_index_data["resources"]} == {
        ("Icon", "home"),
        ("AssetImage", "cover"),
    }

    update_response = await authenticated_client.patch(
        f"/api/pages/{page_id}",
        json={
            "page_content": """
<template>
  <section>
    <Icon :name="iconName" />
    <AssetMermaid :name="'graph'" />
  </section>
</template>
            """.strip(),
            "file_type": "vue",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 2

    second_index_response = await authenticated_client.get(f"/api/pages/{page_id}/component-index")
    assert second_index_response.status_code == 200
    second_index_data = second_index_response.json()
    assert second_index_data["current_version_no"] == 2
    assert set(second_index_data["components"]) == {"Icon", "AssetMermaid"}
    assert {(item["component_name"], item["resource_name"]) for item in second_index_data["resources"]} == {
        ("Icon", "__DYNAMIC__"),
        ("AssetMermaid", "graph"),
    }
