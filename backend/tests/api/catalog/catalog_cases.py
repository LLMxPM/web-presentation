"""文件功能：验证工作空间、项目和页面资源库的 CRUD 及编码自动生成。"""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.page import Page
from app.schemas.project_app_config import DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN


async def _create_catalog_workspace(client: AsyncClient, name: str) -> dict:
    """创建测试工作空间并返回响应 JSON。"""

    response = await client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()


async def _create_catalog_project(
    client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    status: str = "active",
) -> dict:
    """创建测试项目并返回响应 JSON。"""

    response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": status},
    )
    assert response.status_code == 200
    return response.json()


async def _create_catalog_page(
    client: AsyncClient,
    workspace_id: int,
    project_id: int,
    title: str,
    *,
    page_content: str = "<template><div>copy-page</div></template>",
    summary: str | None = None,
    status: str = "active",
) -> dict:
    """创建测试页面并返回响应 JSON。"""

    response = await client.post(
        "/api/pages",
        json={
            "page_content": page_content,
            "file_type": "vue",
            "title": title,
            "summary": summary,
            "status": status,
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_workspace_project_and_page_crud(authenticated_client: AsyncClient) -> None:
    """应能完成工作空间、项目、页面的创建（编码自动生成）、查询、更新和删除。"""

    # 创建工作空间（不传 code，由后端自动生成）
    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "演示工作空间", "description": "test", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_data = workspace_response.json()
    workspace_id = workspace_data["id"]
    assert workspace_data["code"].startswith("WS")
    assert "component_preview_default_config" not in workspace_data

    # 创建项目（不传 code，由后端自动生成）
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "演示项目",
            "description": "project",
            "status": "active",
        },
    )
    assert project_response.status_code == 200
    project_data = project_response.json()
    project_id = project_data["id"]
    assert project_data["code"].startswith("PRJ")
    assert project_data["page_width"] == 1920
    assert project_data["page_height"] == 1080
    assert project_data["base_font_size"] == "20px"
    assert "icon_default_size" not in project_data
    assert project_data["icon_default_stroke_width"] == 2
    assert project_data["show_pdf_export_button"] is True
    assert project_data["menu_mode"] == "preview"
    assert project_data["style_spec_markdown"] == DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN
    assert "themes:" in project_data["theme_config_yaml"]
    assert "icon:" in project_data["theme_config_yaml"]
    assert "baseFontSize" not in project_data["theme_config_yaml"]
    assert "default_size" not in project_data["theme_config_yaml"]

    # 创建页面资源（不传 code，由后端自动生成；使用 page_content 替代 name/slug）
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "demo-page",
            "file_type": "vue",
            "title": "页面标题",
            "summary": "summary",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page_data = page_response.json()
    page_id = page_data["id"]
    assert page_data["code"].startswith("PG")
    assert page_data["page_content"] == "demo-page"
    assert page_data["file_type"] == "vue"
    assert page_data["current_version_no"] == 1

    # 查询单个页面详情
    page_detail_response = await authenticated_client.get(f"/api/pages/{page_id}")
    assert page_detail_response.status_code == 200
    assert page_detail_response.json()["id"] == page_id
    assert page_detail_response.json()["page_content"] == "demo-page"
    assert page_detail_response.json()["file_type"] == "vue"
    assert page_detail_response.json()["current_version_no"] == 1

    # 创建页面时应统一将 CRLF 规范为 LF
    crlf_page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template>\r\n  <div>crlf</div>\r\n</template>\r\n",
            "file_type": "vue",
            "title": "CRLF 页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert crlf_page_response.status_code == 200
    crlf_page_id = crlf_page_response.json()["id"]
    assert crlf_page_response.json()["page_content"] == "<template>\n  <div>crlf</div>\n</template>\n"

    # 按工作空间筛选项目
    projects_response = await authenticated_client.get(f"/api/projects?workspace_id={workspace_id}")
    assert projects_response.status_code == 200
    assert projects_response.json()["items"][0]["workspace_id"] == workspace_id

    # 更新项目名称
    update_project_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"name": "演示项目-更新"},
    )
    assert update_project_response.status_code == 200
    assert update_project_response.json()["name"] == "演示项目-更新"

    # 更新页面标题
    update_page_response = await authenticated_client.patch(
        f"/api/pages/{page_id}",
        json={"title": "页面标题-更新"},
    )
    assert update_page_response.status_code == 200
    assert update_page_response.json()["title"] == "页面标题-更新"

    normalize_page_response = await authenticated_client.patch(
        f"/api/pages/{crlf_page_id}",
        json={"page_content": "<template>\r\n  <div>updated</div>\r\n</template>\r\n"},
    )
    assert normalize_page_response.status_code == 200
    assert normalize_page_response.json()["page_content"] == "<template>\n  <div>updated</div>\n</template>\n"

    # 删除页面资源仍需在所属工作空间可访问时完成
    delete_page_response = await authenticated_client.delete(f"/api/pages/{page_id}")
    assert delete_page_response.status_code == 200

    # 工作空间下有项目时不允许删除
    delete_workspace_response = await authenticated_client.delete(f"/api/workspaces/{workspace_id}")
    assert delete_workspace_response.status_code == 409

    # 先删除项目
    delete_project_response = await authenticated_client.delete(f"/api/projects/{project_id}")
    assert delete_project_response.status_code == 200

    # 项目删除后才能删除工作空间
    delete_workspace_response = await authenticated_client.delete(f"/api/workspaces/{workspace_id}")
    assert delete_workspace_response.status_code == 200


async def test_auto_generated_codes_are_unique(authenticated_client: AsyncClient) -> None:
    """连续创建多个同类型资源时，自动生成的编码应各不相同。"""

    # 连续创建两个工作空间
    ws1 = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "工作空间1", "status": "active"},
    )
    assert ws1.status_code == 200
    ws2 = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "工作空间2", "status": "active"},
    )
    assert ws2.status_code == 200
    assert ws1.json()["code"] != ws2.json()["code"]

    # 连续创建两个项目
    workspace_id = ws1.json()["id"]
    p1 = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "项目1", "status": "active"},
    )
    assert p1.status_code == 200
    p2 = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "项目2", "status": "active"},
    )
    assert p2.status_code == 200
    assert p1.json()["code"] != p2.json()["code"]

    # 连续创建两个页面
    pg1 = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "page-a",
            "file_type": "vue",
            "title": "页面A",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": p1.json()["id"],
        },
    )
    assert pg1.status_code == 200
    pg2 = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "page-b",
            "file_type": "ts",
            "title": "页面B",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": p1.json()["id"],
        },
    )
    assert pg2.status_code == 200
    assert pg1.json()["code"] != pg2.json()["code"]


async def test_project_config_update_should_reject_invalid_structured_fields(authenticated_client: AsyncClient) -> None:
    """项目结构化运行时字段应支持页面规格归一化，并拒绝非法值。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "配置工作空间", "status": "active"},
    )
    assert workspace.status_code == 200

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace.json()["id"], "name": "配置项目", "status": "active"},
    )
    assert project.status_code == 200

    response = await authenticated_client.patch(
        f"/api/projects/{project.json()['id']}",
        json={"page_width": 0},
    )

    assert response.status_code == 422

    normalized_response = await authenticated_client.patch(
        f"/api/projects/{project.json()['id']}",
        json={
            "base_font_size": "18",
            "icon_default_stroke_width": 3,
        },
    )
    assert normalized_response.status_code == 200
    assert normalized_response.json()["base_font_size"] == "18px"
    assert "icon_default_size" not in normalized_response.json()
    assert normalized_response.json()["icon_default_stroke_width"] == 3

    invalid_font_response = await authenticated_client.patch(
        f"/api/projects/{project.json()['id']}",
        json={"base_font_size": "0px"},
    )
    assert invalid_font_response.status_code == 422

    invalid_icon_response = await authenticated_client.patch(
        f"/api/projects/{project.json()['id']}",
        json={"icon_default_size": 0},
    )
    assert invalid_icon_response.status_code == 422


async def test_project_menu_mode_should_support_bottom_preview(authenticated_client: AsyncClient) -> None:
    """项目菜单模式应允许配置 Runtime 新增的底部缩略图模式。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "底部菜单工作空间", "status": "active"},
    )
    assert workspace.status_code == 200

    project = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace.json()["id"],
            "name": "底部菜单项目",
            "status": "active",
            "menu_mode": "bottom-preview",
        },
    )
    assert project.status_code == 200
    assert project.json()["menu_mode"] == "bottom-preview"

    config_response = await authenticated_client.get(
        f"/api/runtime/projects/{project.json()['id']}/configs/app.config.yaml",
    )
    assert config_response.status_code == 200
    assert "menuMode: bottom-preview" in config_response.text

    update_response = await authenticated_client.patch(
        f"/api/projects/{project.json()['id']}",
        json={"menu_mode": "text"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["menu_mode"] == "text"


async def test_project_archive_and_restore_should_maintain_archived_at(authenticated_client: AsyncClient) -> None:
    """项目归档后应记录归档时间，恢复后应清空，并支持按归档状态筛选。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "归档测试工作空间", "status": "active"},
    )
    assert workspace.status_code == 200
    workspace_id = workspace.json()["id"]

    project = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "待归档项目", "status": "active"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]
    assert project.json()["archived_at"] is None

    archive_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200
    archived_at = archive_response.json()["archived_at"]
    assert archived_at is not None

    active_list_response = await authenticated_client.get(
        f"/api/projects?workspace_id={workspace_id}&status=active",
    )
    assert active_list_response.status_code == 200
    assert active_list_response.json()["items"] == []

    archived_list_response = await authenticated_client.get(
        f"/api/projects?workspace_id={workspace_id}&status=archived&sort_by=archived_at&sort_order=desc",
    )
    assert archived_list_response.status_code == 200
    archived_item = archived_list_response.json()["items"][0]
    assert archived_item["id"] == project_id
    assert archived_item["archived_at"] is not None

    restore_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"status": "active"},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["archived_at"] is None


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


async def test_page_content_accepts_long_text(authenticated_client: AsyncClient) -> None:
    """页面代码应支持长文本创建和更新。"""

    workspace = await _create_catalog_workspace(authenticated_client, "长文本页面空间")
    project = await _create_catalog_project(authenticated_client, workspace["id"], "长文本页面项目")
    long_page_content = "<template>\n" + ("<section>monaco</section>\n" * 40) + "</template>"

    create_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": long_page_content,
            "file_type": "vue",
            "title": "长文本页面",
            "status": "active",
            "workspace_id": workspace["id"],
            "project_id": project["id"],
        },
    )
    assert create_response.status_code == 200

    page_id = create_response.json()["id"]
    assert create_response.json()["page_content"] == long_page_content

    updated_page_content = long_page_content + "\n<script setup lang=\"ts\">\nconst value = 'saved'\n</script>"
    update_response = await authenticated_client.patch(
        f"/api/pages/{page_id}",
        json={"page_content": updated_page_content, "file_type": "ts"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["page_content"] == updated_page_content
    assert update_response.json()["file_type"] == "ts"
    assert update_response.json()["current_version_no"] == 2


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
            "change_note": "增加脚本逻辑",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 2

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
    assert snapshot_response.json()["storage_type"] == "snapshot"

    restored_response = await authenticated_client.post(
        f"/api/pages/{page_id}/versions/1/restore",
        json={"change_note": "回滚到稳定版本"},
    )
    assert restored_response.status_code == 200
    restored_page = restored_response.json()
    assert restored_page["current_version_no"] == 3
    assert restored_page["page_content"] == "<template><div>v1</div></template>"
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


async def test_workspace_component_should_persist_component_type_and_support_filter(authenticated_client: AsyncClient) -> None:
    """工作空间组件应保存 component_type，并支持列表过滤与更新。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件类型工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>card</div></template>",
            "file_type": "vue",
            "summary": "展示统计信息",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_data = create_response.json()
    assert component_data["component_type"] == "内容区块"
    assert component_data["import_name"] == "StatsCard"

    update_response = await authenticated_client.patch(
        f"/api/components/{component_data['id']}",
        json={
            "import_name": "StatsResourceCard",
            "component_type": "数据展示",
            "change_note": "补充组件类型",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["component_type"] == "数据展示"
    assert update_response.json()["import_name"] == "StatsResourceCard"

    filtered_response = await authenticated_client.get(
        "/api/components",
        params={"workspace_id": workspace_id, "component_type": "数据展示"},
    )
    assert filtered_response.status_code == 200
    assert filtered_response.json()["items"][0]["component_type"] == "数据展示"
    assert filtered_response.json()["items"][0]["import_name"] == "StatsResourceCard"


async def test_workspace_component_import_name_should_be_required_valid_and_unique(authenticated_client: AsyncClient) -> None:
    """工作空间组件引用名应必填、符合 PascalCase，并在同一工作空间启用组件内唯一。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件引用名工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    missing_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "缺少引用名组件",
            "content": "<template><div>missing</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert missing_response.status_code == 422

    invalid_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "非法引用名组件",
            "import_name": "stats-card",
            "content": "<template><div>invalid</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert invalid_response.status_code == 422

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>card</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200

    duplicate_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "重复统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>duplicate</div></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "COMPONENT_IMPORT_NAME_CONFLICT"

    archived_duplicate_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "归档重复统计卡片",
            "import_name": "StatsCard",
            "content": "<template><div>archived</div></template>",
            "file_type": "vue",
            "status": "archived",
        },
    )
    assert archived_duplicate_response.status_code == 200


async def test_workspace_component_should_reject_unknown_component_type(authenticated_client: AsyncClient) -> None:
    """工作空间组件仅允许使用固定组件分类。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "固定组件分类工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_response.json()["id"],
            "name": "自由分类组件",
            "import_name": "FreeCategoryComponent",
            "content": "<template><div>demo</div></template>",
            "file_type": "vue",
            "component_type": "card",
            "status": "active",
        },
    )
    assert create_response.status_code == 422


async def test_component_package_import_should_return_imported_components(authenticated_client: AsyncClient) -> None:
    """组件分享包导入后应直接返回已导入组件，不能触发异步 ORM 隐式加载。"""

    source_workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件导出工作空间", "status": "active"},
    )
    assert source_workspace_response.status_code == 200
    source_workspace_id = source_workspace_response.json()["id"]
    target_workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "组件导入工作空间", "status": "active"},
    )
    assert target_workspace_response.status_code == 200
    target_workspace_id = target_workspace_response.json()["id"]

    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": source_workspace_id,
            "name": "导出卡片",
            "import_name": "ExportedCard",
            "component_type": "内容区块",
            "content": "<template><section>exported</section></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": "导出版"},
    )
    assert publish_response.status_code == 200

    export_response = await authenticated_client.post(
        "/api/components/export-package",
        json={"workspace_id": source_workspace_id, "component_ids": [component_id]},
    )
    assert export_response.status_code == 200

    import_response = await authenticated_client.post(
        "/api/components/import-package",
        data={"workspace_id": str(target_workspace_id)},
        files={"archive": ("components.zip", export_response.content, "application/zip")},
    )
    assert import_response.status_code == 200
    imported_components = import_response.json()["imported_components"]
    assert len(imported_components) == 1
    assert imported_components[0]["workspace_id"] == target_workspace_id
    assert imported_components[0]["name"] == "导出卡片"
    assert imported_components[0]["import_name"] == "ExportedCard"
    assert imported_components[0]["component_type"] == "内容区块"
    assert imported_components[0]["current_version_no"] == 1
