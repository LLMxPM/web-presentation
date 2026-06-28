"""文件功能：承载 catalog routes versioning 场景的拆分测试用例。"""

from __future__ import annotations

from tests.api.catalog.catalog_cases import *  # noqa: F403


async def test_project_route_tree_should_accept_page_bindings(authenticated_client: AsyncClient) -> None:
    """项目路由树应支持绑定页面，并在页面接口中返回纳管状态。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "路由工作空间", "status": "active"},
    )
    assert workspace.status_code == 200

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace.json()["id"], "name": "路由项目", "status": "active"},
    )
    assert project.status_code == 200

    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-page</div></template>",
            "file_type": "vue",
            "title": "路由首页",
            "status": "active",
            "workspace_id": workspace.json()["id"],
            "project_id": project.json()["id"],
        },
    )
    assert page.status_code == 200

    response = await authenticated_client.put(
        f"/api/projects/{project.json()['id']}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page.json()["id"],
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["routes"][0]["display_title"] == "路由首页"
    assert response.json()["routes"][0]["page_code"] == page.json()["code"]

    page_list_response = await authenticated_client.get(f"/api/pages?project_id={project.json()['id']}")
    assert page_list_response.status_code == 200
    listed_page = page_list_response.json()["items"][0]
    assert listed_page["is_in_project_route"] is True
    assert listed_page["route_bindings"] == [
        {
            "route_id": response.json()["routes"][0]["id"],
            "parent_route": None,
            "route": "home",
            "full_path": "/home",
            "parent_order": None,
            "order": 0,
        }
    ]

async def test_archiving_page_should_remove_project_route_bindings(authenticated_client: AsyncClient) -> None:
    """页面归档时应从项目路由配置中移除，并保留其他页面路由。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "页面归档路由工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "页面归档路由项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    archived_page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>archive me</div></template>",
            "file_type": "vue",
            "title": "待归档页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert archived_page.status_code == 200
    archived_page_id = archived_page.json()["id"]

    remaining_page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>keep me</div></template>",
            "file_type": "vue",
            "title": "保留页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert remaining_page.status_code == 200
    remaining_page_id = remaining_page.json()["id"]

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "cover",
                    "order": 0,
                    "page_id": archived_page_id,
                },
                {
                    "route_type": "group",
                    "route": "chapter",
                    "order": 1,
                    "group_title": "章节",
                    "children": [
                        {
                            "route": "archived",
                            "order": 0,
                            "page_id": archived_page_id,
                        },
                        {
                            "route": "remaining",
                            "order": 1,
                            "page_id": remaining_page_id,
                        },
                    ],
                },
            ],
        },
    )
    assert route_response.status_code == 200

    archive_response = await authenticated_client.patch(
        f"/api/pages/{archived_page_id}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    routes_after_archive = await authenticated_client.get(f"/api/projects/{project_id}/routes")
    assert routes_after_archive.status_code == 200
    assert routes_after_archive.json()["routes"] == [
        {
            "id": routes_after_archive.json()["routes"][0]["id"],
            "route_type": "group",
            "route": "chapter",
            "order": 1,
            "hidden": False,
            "group_title": "章节",
            "page_id": None,
            "page_code": None,
            "page_title": None,
            "display_title": "章节",
            "children": [
                {
                    "id": routes_after_archive.json()["routes"][0]["children"][0]["id"],
                    "route_type": "page",
                    "route": "remaining",
                    "order": 1,
                    "hidden": False,
                    "page_id": remaining_page_id,
                    "page_code": remaining_page.json()["code"],
                    "page_title": "保留页面",
                    "display_title": "保留页面",
                }
            ],
        }
    ]

    archived_list_response = await authenticated_client.get(
        f"/api/pages?project_id={project_id}&status=archived",
    )
    assert archived_list_response.status_code == 200
    archived_item = archived_list_response.json()["items"][0]
    assert archived_item["id"] == archived_page_id
    assert archived_item["is_in_project_route"] is False
    assert archived_item["route_bindings"] == []

async def test_page_copy_to_project_should_create_current_version_only(
    authenticated_client: AsyncClient,
) -> None:
    """页面复制应只复制当前源码和基础信息，不携带历史版本与截图。"""

    workspace = await _create_catalog_workspace(authenticated_client, "页面复制工作空间")
    source_project = await _create_catalog_project(authenticated_client, workspace["id"], "源项目")
    target_project = await _create_catalog_project(authenticated_client, workspace["id"], "目标项目")
    source_page = await _create_catalog_page(
        authenticated_client,
        workspace["id"],
        source_project["id"],
        "源页面",
        page_content="<template><div>v1</div></template>",
        summary="源摘要",
        speaker_notes="源页面演讲备注",
    )

    update_response = await authenticated_client.patch(
        f"/api/pages/{source_page['id']}",
        json={
            "page_content": "<template><div>v2</div></template>",
            "change_note": "更新到当前版本",
        },
    )
    assert update_response.status_code == 200

    async with get_session_factory()() as session:
        source_model = await session.get(Page, source_page["id"])
        assert source_model is not None
        source_model.screenshot_storage_key = "page-screenshots/source.png"
        source_model.screenshot_version_no = 2
        source_model.screenshot_config_hash = "source-hash"
        source_model.screenshot_updated_at = datetime.now(UTC)
        await session.commit()

    copy_response = await authenticated_client.post(
        f"/api/pages/{source_page['id']}/copy-to-project",
        json={
            "target_project_id": target_project["id"],
            "title": "复制页面",
            "summary": None,
        },
    )

    assert copy_response.status_code == 200
    copied_page = copy_response.json()
    assert copied_page["id"] != source_page["id"]
    assert copied_page["code"] != source_page["code"]
    assert copied_page["workspace_id"] == workspace["id"]
    assert copied_page["project_id"] == target_project["id"]
    assert copied_page["title"] == "复制页面"
    assert copied_page["summary"] is None
    assert copied_page["speaker_notes"] == "源页面演讲备注"
    assert copied_page["page_content"] == "<template><div>v2</div></template>"
    assert copied_page["current_version_no"] == 1
    assert copied_page["screenshot_url"] is None
    assert copied_page["screenshot_version_no"] is None
    assert copied_page["route_bindings"] == []
    assert copied_page["is_in_project_route"] is False

    source_detail_response = await authenticated_client.get(f"/api/pages/{source_page['id']}")
    assert source_detail_response.status_code == 200
    source_detail = source_detail_response.json()
    assert source_detail["project_id"] == source_project["id"]
    assert source_detail["current_version_no"] == 2
    assert source_detail["screenshot_url"] is not None

    source_versions_response = await authenticated_client.get(f"/api/pages/{source_page['id']}/versions")
    copied_versions_response = await authenticated_client.get(f"/api/pages/{copied_page['id']}/versions")
    assert source_versions_response.status_code == 200
    assert copied_versions_response.status_code == 200
    assert len(source_versions_response.json()) == 2
    assert len(copied_versions_response.json()) == 1
    assert copied_versions_response.json()[0]["version_no"] == 1

async def test_page_copy_to_project_should_validate_scope_and_status(
    authenticated_client: AsyncClient,
) -> None:
    """页面复制应拒绝同项目、跨工作空间和非启用状态。"""

    workspace = await _create_catalog_workspace(authenticated_client, "复制范围工作空间")
    other_workspace = await _create_catalog_workspace(authenticated_client, "复制范围其他工作空间")
    source_project = await _create_catalog_project(authenticated_client, workspace["id"], "源项目")
    target_project = await _create_catalog_project(authenticated_client, workspace["id"], "目标项目")
    other_project = await _create_catalog_project(authenticated_client, other_workspace["id"], "其他空间项目")
    source_page = await _create_catalog_page(authenticated_client, workspace["id"], source_project["id"], "范围源页面")

    same_project_response = await authenticated_client.post(
        f"/api/pages/{source_page['id']}/copy-to-project",
        json={"target_project_id": source_project["id"]},
    )
    assert same_project_response.status_code == 400
    assert same_project_response.json()["code"] == "PAGE_COPY_TARGET_SAME_PROJECT"

    cross_workspace_response = await authenticated_client.post(
        f"/api/pages/{source_page['id']}/copy-to-project",
        json={"target_project_id": other_project["id"]},
    )
    assert cross_workspace_response.status_code == 400
    assert cross_workspace_response.json()["code"] == "PAGE_COPY_WORKSPACE_MISMATCH"

    inactive_target = await _create_catalog_project(authenticated_client, workspace["id"], "归档目标项目")
    archive_target_response = await authenticated_client.patch(
        f"/api/projects/{inactive_target['id']}",
        json={"status": "archived"},
    )
    assert archive_target_response.status_code == 200
    inactive_target_response = await authenticated_client.post(
        f"/api/pages/{source_page['id']}/copy-to-project",
        json={"target_project_id": inactive_target["id"]},
    )
    assert inactive_target_response.status_code == 400
    assert inactive_target_response.json()["code"] == "PAGE_COPY_TARGET_PROJECT_INACTIVE"

    archive_source_response = await authenticated_client.patch(
        f"/api/pages/{source_page['id']}",
        json={"status": "archived"},
    )
    assert archive_source_response.status_code == 200
    inactive_source_response = await authenticated_client.post(
        f"/api/pages/{source_page['id']}/copy-to-project",
        json={"target_project_id": target_project["id"]},
    )
    assert inactive_source_response.status_code == 400
    assert inactive_source_response.json()["code"] == "PAGE_COPY_SOURCE_INACTIVE"

async def test_page_copy_to_project_should_append_routes_and_deduplicate(
    authenticated_client: AsyncClient,
) -> None:
    """复制页面时可追加顶层或分组路由，并自动消解同级 route 冲突。"""

    workspace = await _create_catalog_workspace(authenticated_client, "复制路由工作空间")
    source_project = await _create_catalog_project(authenticated_client, workspace["id"], "源项目")
    target_project = await _create_catalog_project(authenticated_client, workspace["id"], "目标项目")
    existing_root_page = await _create_catalog_page(authenticated_client, workspace["id"], target_project["id"], "目标首页")
    existing_group_page = await _create_catalog_page(authenticated_client, workspace["id"], target_project["id"], "目标章节页")
    root_source_page = await _create_catalog_page(authenticated_client, workspace["id"], source_project["id"], "复制到顶层")
    group_source_page = await _create_catalog_page(authenticated_client, workspace["id"], source_project["id"], "复制到分组")

    route_response = await authenticated_client.put(
        f"/api/projects/{target_project['id']}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": existing_root_page["id"],
                },
                {
                    "route_type": "group",
                    "route": "chapter",
                    "order": 10,
                    "group_title": "章节",
                    "children": [
                        {
                            "route": "home",
                            "order": 0,
                            "page_id": existing_group_page["id"],
                        }
                    ],
                },
            ]
        },
    )
    assert route_response.status_code == 200
    group_id = route_response.json()["routes"][1]["id"]

    root_copy_response = await authenticated_client.post(
        f"/api/pages/{root_source_page['id']}/copy-to-project",
        json={
            "target_project_id": target_project["id"],
            "route_placement": "root",
            "route": "home",
        },
    )
    assert root_copy_response.status_code == 200
    root_copy = root_copy_response.json()
    assert root_copy["route_bindings"][0]["full_path"] == "/home-2"
    assert root_copy["route_bindings"][0]["order"] == 20

    group_copy_response = await authenticated_client.post(
        f"/api/pages/{group_source_page['id']}/copy-to-project",
        json={
            "target_project_id": target_project["id"],
            "route_placement": "group",
            "parent_route_id": group_id,
            "route": "home",
        },
    )
    assert group_copy_response.status_code == 200
    group_copy = group_copy_response.json()
    assert group_copy["route_bindings"][0]["parent_route"] == "chapter"
    assert group_copy["route_bindings"][0]["full_path"] == "/chapter/home-2"
    assert group_copy["route_bindings"][0]["order"] == 10

    routes_after_copy = await authenticated_client.get(f"/api/projects/{target_project['id']}/routes")
    assert routes_after_copy.status_code == 200
    root_routes = routes_after_copy.json()["routes"]
    assert root_routes[2]["route"] == "home-2"
    assert root_routes[2]["hidden"] is False
    assert root_routes[1]["children"][1]["route"] == "home-2"
    assert root_routes[1]["children"][1]["hidden"] is False

async def test_page_copy_to_project_should_reject_page_module_dependency_and_invalid_group_atomically(
    authenticated_client: AsyncClient,
) -> None:
    """复制应阻断页面模块依赖，非法目标分组也不能留下半成品页面。"""

    workspace = await _create_catalog_workspace(authenticated_client, "复制原子性工作空间")
    source_project = await _create_catalog_project(authenticated_client, workspace["id"], "源项目")
    target_project = await _create_catalog_project(authenticated_client, workspace["id"], "目标项目")
    module_page = await _create_catalog_page(
        authenticated_client,
        workspace["id"],
        source_project["id"],
        "含页面模块依赖",
        page_content="""
<template><OtherPage /></template>
<script setup>
import OtherPage from './OtherPage.vue'
</script>
""".strip(),
    )

    dependency_response = await authenticated_client.post(
        f"/api/pages/{module_page['id']}/copy-to-project",
        json={"target_project_id": target_project["id"]},
    )
    assert dependency_response.status_code == 400
    assert dependency_response.json()["code"] == "PAGE_COPY_PAGE_MODULE_DEPENDENCY_UNSUPPORTED"

    clean_page = await _create_catalog_page(authenticated_client, workspace["id"], source_project["id"], "非法分组复制源")
    before_list_response = await authenticated_client.get(f"/api/pages?project_id={target_project['id']}")
    assert before_list_response.status_code == 200
    before_total = before_list_response.json()["total"]

    invalid_group_response = await authenticated_client.post(
        f"/api/pages/{clean_page['id']}/copy-to-project",
        json={
            "target_project_id": target_project["id"],
            "route_placement": "group",
            "parent_route_id": 999999,
        },
    )
    assert invalid_group_response.status_code == 400
    assert invalid_group_response.json()["code"] == "PAGE_COPY_ROUTE_GROUP_INVALID"

    after_list_response = await authenticated_client.get(f"/api/pages?project_id={target_project['id']}")
    assert after_list_response.status_code == 200
    assert after_list_response.json()["total"] == before_total

async def test_project_route_tree_should_reject_duplicate_top_level_route(
    authenticated_client: AsyncClient,
) -> None:
    """项目路由树应拒绝重复的顶层 route。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "路由编码工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "路由编码项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-by-code</div></template>",
            "file_type": "vue",
            "title": "按编码绑定页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page.status_code == 200
    page_data = page.json()

    update_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page_data["id"],
                },
                {
                    "route_type": "group",
                    "route": "home",
                    "order": 10,
                    "group_title": "重复分组",
                    "children": [
                        {
                            "route": "child",
                            "order": 0,
                            "page_id": page_data["id"],
                        }
                    ],
                },
            ]
        },
    )

    assert update_response.status_code == 400
    assert update_response.json()["code"] == "PROJECT_ROUTE_DUPLICATE_ROUTE"

async def test_project_route_tree_should_reject_duplicate_child_route(
    authenticated_client: AsyncClient,
) -> None:
    """项目路由树应拒绝同一分组下重复的子 route。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "路由主键工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "路由主键项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-by-id</div></template>",
            "file_type": "vue",
            "title": "按主键绑定页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page.status_code == 200

    second_page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-by-id-2</div></template>",
            "file_type": "vue",
            "title": "按主键绑定页面2",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert second_page.status_code == 200

    update_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "group",
                    "route": "demo",
                    "order": 0,
                    "group_title": "演示分组",
                    "children": [
                        {
                            "route": "child",
                            "order": 0,
                            "page_id": page.json()["id"],
                        },
                        {
                            "route": "child",
                            "order": 10,
                            "page_id": second_page.json()["id"],
                        },
                    ],
                }
            ]
        },
    )

    assert update_response.status_code == 400
    assert update_response.json()["code"] == "PROJECT_ROUTE_DUPLICATE_CHILD_ROUTE"

async def test_project_route_tree_should_reject_invalid_route_segments(
    authenticated_client: AsyncClient,
) -> None:
    """项目路由树应拒绝根路径、前后斜杠、多段路径和包含空格的 route。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "非法路由片段工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "非法路由片段项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>invalid-route</div></template>",
            "file_type": "vue",
            "title": "非法路由页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page.status_code == 200
    page_id = page.json()["id"]

    invalid_root_routes = ["/", "/home", "home/", "a/b", " ", "has space"]
    for route in invalid_root_routes:
        update_response = await authenticated_client.put(
            f"/api/projects/{project_id}/routes",
            json={"routes": [{"route_type": "page", "route": route, "order": 0, "page_id": page_id}]},
        )
        assert update_response.status_code == 400
        assert update_response.json()["code"] == "PROJECT_ROUTE_INVALID_SEGMENT"

    invalid_group_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "group",
                    "route": "/",
                    "order": 0,
                    "group_title": "非法分组",
                    "children": [{"route": "overview", "order": 0, "page_id": page_id}],
                }
            ]
        },
    )
    assert invalid_group_response.status_code == 400
    assert invalid_group_response.json()["code"] == "PROJECT_ROUTE_INVALID_SEGMENT"

    invalid_child_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "group",
                    "route": "chapter",
                    "order": 0,
                    "group_title": "合法分组",
                    "children": [{"route": "a/b", "order": 0, "page_id": page_id}],
                }
            ]
        },
    )
    assert invalid_child_response.status_code == 400
    assert invalid_child_response.json()["code"] == "PROJECT_ROUTE_INVALID_SEGMENT"

async def test_project_route_tree_should_reject_icon_field(authenticated_client: AsyncClient) -> None:
    """项目路由树不再接收 icon 字段。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "路由图标字段工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "路由图标字段项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>route-with-icon-field</div></template>",
            "file_type": "vue",
            "title": "路由图标字段页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page.status_code == 200

    response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "cover",
                    "order": 0,
                    "icon": "file",
                    "page_id": page.json()["id"],
                },
            ]
        },
    )
    assert response.status_code == 422

async def test_project_route_tree_should_accept_single_segment_routes(
    authenticated_client: AsyncClient,
) -> None:
    """项目路由树应接受大小写字母、数字、短横线和下划线组成的单段 route。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "合法路由片段工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "合法路由片段项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    first_page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>single-segment-1</div></template>",
            "file_type": "vue",
            "title": "合法页面一",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert first_page.status_code == 200
    second_page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>single-segment-2</div></template>",
            "file_type": "vue",
            "title": "合法页面二",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert second_page.status_code == 200

    update_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "PAGE_01",
                    "order": 0,
                    "page_id": first_page.json()["id"],
                },
                {
                    "route_type": "group",
                    "route": "chapter-1",
                    "order": 10,
                    "group_title": "第一章",
                    "children": [{"route": "overview_1", "order": 0, "page_id": second_page.json()["id"]}],
                },
            ]
        },
    )

    assert update_response.status_code == 200
    assert [item["route"] for item in update_response.json()["routes"]] == ["PAGE_01", "chapter-1"]
    assert update_response.json()["routes"][1]["children"][0]["route"] == "overview_1"

async def test_runtime_project_config_endpoint_should_return_yaml_text(authenticated_client: AsyncClient) -> None:
    """Runtime 配置下发接口应返回 app YAML，并且不再提供 routes.config.yaml。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "运行时工作空间", "status": "active"},
    )
    assert workspace.status_code == 200

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace.json()["id"], "name": "运行时项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    config_response = await authenticated_client.get(f"/api/runtime/projects/{project_id}/configs/app.config.yaml")
    assert config_response.status_code == 200
    assert config_response.headers["content-type"].startswith("text/yaml")
    assert "app:" in config_response.text
    assert "title: 运行时项目" in config_response.text
    assert "icon: slider" in config_response.text
    assert "baseFontSize: 20px" in config_response.text
    assert "iconDefaultSize" not in config_response.text
    assert "iconDefaultStrokeWidth: 2" in config_response.text
    assert "version:" not in config_response.text

    route_config_response = await authenticated_client.get(f"/api/runtime/projects/{project_id}/configs/routes.config.yaml")
    assert route_config_response.status_code == 404

    archive_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200

    archived_config_response = await authenticated_client.get(f"/api/runtime/projects/{project_id}/configs/app.config.yaml")
    assert archived_config_response.status_code == 409
    assert archived_config_response.json()["code"] == "PROJECT_NOT_ACTIVE"

async def test_runtime_project_icon_should_follow_theme_config(authenticated_client: AsyncClient) -> None:
    """项目运行时图标应从当前主题配置解析。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "主题图标工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    icon_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("theme-app-icon.svg", b"<svg><path d='theme-app-icon'/></svg>", "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert icon_response.status_code == 200
    icon_asset_id = icon_response.json()["id"]

    theme_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/themes",
        json={
            "key": "custom",
            "name": "自定义主题",
            "description": "带项目图标的主题",
            "project_icon_asset_id": icon_asset_id,
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

    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "主题图标项目",
            "status": "active",
            "theme_key": "custom",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    config_response = await authenticated_client.get(f"/api/runtime/projects/{project_id}/configs/app.config.yaml")
    assert config_response.status_code == 200
    assert "icon: theme-app-icon" in config_response.text

async def test_page_version_history_snapshot_and_restore(authenticated_client: AsyncClient) -> None:
    """页面应支持版本链查询、重点快照创建和历史版本恢复。"""

    workspace = await _create_catalog_workspace(authenticated_client, "版本页面空间")
    project = await _create_catalog_project(authenticated_client, workspace["id"], "版本页面项目")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>v1</div></template>",
            "file_type": "vue",
            "title": "版本页面",
            "speaker_notes": "讲解 V1 的核心结论。",
            "status": "active",
            "workspace_id": workspace["id"],
            "project_id": project["id"],
        },
    )
    assert create_response.status_code == 200
    page_id = create_response.json()["id"]
    assert create_response.json()["current_version_no"] == 1

    update_response = await authenticated_client.patch(
        f"/api/pages/{page_id}",
        json={
            "page_content": "<template><div>v2</div></template>\n<script setup lang=\"ts\">\nconst version = 2\n</script>",
            "file_type": "ts",
            "speaker_notes": "讲解 V2 新增逻辑。",
            "change_note": "增加脚本逻辑",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 2
    assert update_response.json()["speaker_notes"] == "讲解 V2 新增逻辑。"

    versions_response = await authenticated_client.get(f"/api/pages/{page_id}/versions")
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert [item["version_no"] for item in versions] == [2, 1]
    assert re.fullmatch(r"\d{8}-\d{6}", versions[0]["version_label"])
    assert versions[0]["is_current"] is True
    assert versions[0]["storage_type"] == "snapshot"
    assert re.fullmatch(r"\d{8}-\d{6}", versions[1]["version_label"])
    assert versions[1]["storage_type"] == "diff"
    assert versions[0]["change_note"] == "增加脚本逻辑"

    version_1_response = await authenticated_client.get(f"/api/pages/{page_id}/versions/1")
    assert version_1_response.status_code == 200
    assert version_1_response.json()["content_mode"] == "diff"
    assert f"--- {version_1_response.json()['version_label']}\n" in version_1_response.json()["content"]
    assert f"+++ {versions[0]['version_label']}\n" in version_1_response.json()["content"]
    assert "-<template><div>v1</div></template>" in version_1_response.json()["content"]
    assert "+<template><div>v2</div></template>" in version_1_response.json()["content"]
    assert version_1_response.json()["resolved_content"] == "<template><div>v1</div></template>"
    assert version_1_response.json()["speaker_notes"] == "讲解 V1 的核心结论。"
    assert re.fullmatch(r"\d{8}-\d{6}", version_1_response.json()["version_label"])
    assert version_1_response.json()["storage_type"] == "diff"

    snapshot_response = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "里程碑 V1"},
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["is_important"] is True
    assert snapshot_response.json()["version_label"] == "V1"
    assert snapshot_response.json()["snapshot_name"] == "里程碑 V1"
    assert snapshot_response.json()["content_mode"] == "full"
    assert snapshot_response.json()["resolved_content"] == "<template><div>v1</div></template>"
    assert snapshot_response.json()["speaker_notes"] == "讲解 V1 的核心结论。"
    assert snapshot_response.json()["storage_type"] == "snapshot"

    restored_response = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/1/restore",
        json={"change_note": "回滚到稳定版本"},
    )
    assert restored_response.status_code == 200
    restored_page = restored_response.json()
    assert restored_page["current_version_no"] == 3
    assert restored_page["page_content"] == "<template><div>v1</div></template>"
    assert restored_page["speaker_notes"] == "讲解 V1 的核心结论。"
    assert restored_page["file_type"] == "vue"

    versions_after_restore = await authenticated_client.get(f"/api/pages/{page_id}/versions")
    assert versions_after_restore.status_code == 200
    versions_data = versions_after_restore.json()
    assert [item["version_no"] for item in versions_data] == [3, 2, 1]
    assert re.fullmatch(r"\d{8}-\d{6}", versions_data[0]["version_label"])
    assert versions_data[0]["is_current"] is True
    assert versions_data[1]["storage_type"] == "diff"
    assert versions_data[2]["is_important"] is True
    assert versions_data[2]["version_label"] == "V1"

async def test_snapshot_version_labels_support_major_and_sub_versions(authenticated_client: AsyncClient) -> None:
    """快照版本应支持 V1/V2 主版本和 1.1/1.11 子版本命名。"""

    workspace = await _create_catalog_workspace(authenticated_client, "快照编号空间")
    project = await _create_catalog_project(authenticated_client, workspace["id"], "快照编号项目")
    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>v1</div></template>",
            "file_type": "vue",
            "title": "快照编号页面",
            "status": "active",
            "workspace_id": workspace["id"],
            "project_id": project["id"],
        },
    )
    assert create_response.status_code == 200
    page_id = create_response.json()["id"]

    for idx in range(2, 6):
        update_response = await authenticated_client.patch(
            f"/api/pages/{page_id}",
            json={
                "page_content": f"<template><div>v{idx}</div></template>",
                "file_type": "vue",
                "change_note": f"更新到 v{idx}",
            },
        )
        assert update_response.status_code == 200

    snapshot_v1 = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "主快照 1"},
    )
    assert snapshot_v1.status_code == 200
    assert snapshot_v1.json()["version_label"] == "V1"

    snapshot_v2 = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/5/snapshot",
        json={"snapshot_name": "主快照 2"},
    )
    assert snapshot_v2.status_code == 200
    assert snapshot_v2.json()["version_label"] == "V2"

    snapshot_sub_1 = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/3/snapshot",
        json={"snapshot_name": "子快照 1"},
    )
    assert snapshot_sub_1.status_code == 200
    assert snapshot_sub_1.json()["version_label"] == "1.1"

    snapshot_sub_2 = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/4/snapshot",
        json={"snapshot_name": "子快照 2"},
    )
    assert snapshot_sub_2.status_code == 200
    assert snapshot_sub_2.json()["version_label"] == "1.11"

async def test_page_version_timestamp_label_should_follow_app_timezone(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """普通保存版本号应按 APP_TIMEZONE 对 created_at 进行格式化。"""

    from app.core.config import get_settings

    workspace = await _create_catalog_workspace(authenticated_client, "时区页面空间")
    project = await _create_catalog_project(authenticated_client, workspace["id"], "时区页面项目")
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Tokyo")
    get_settings.cache_clear()

    try:
        create_response = await authenticated_client.post(
            "/api/pages",
            json={
                "page_content": "<template><div>timezone</div></template>",
                "file_type": "vue",
                "title": "时区页面",
                "status": "active",
                "workspace_id": workspace["id"],
                "project_id": project["id"],
            },
        )
        assert create_response.status_code == 200
        page_id = create_response.json()["id"]

        versions_response = await authenticated_client.get(f"/api/pages/{page_id}/versions")
        assert versions_response.status_code == 200
        version = versions_response.json()[0]

        created_at = datetime.fromisoformat(version["created_at"].replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        expected_label = created_at.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d-%H%M%S")
        assert version["version_label"] == expected_label
    finally:
        get_settings.cache_clear()
