"""文件功能：承载 catalog workspace project page 场景的拆分测试用例。"""

from __future__ import annotations

from tests.api.catalog.catalog_cases import *  # noqa: F403


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
            "speaker_notes": "开场介绍本页目标。",
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
    assert page_data["speaker_notes"] == "开场介绍本页目标。"
    assert page_data["file_type"] == "vue"
    assert page_data["current_version_no"] == 1

    # 查询单个页面详情
    page_detail_response = await authenticated_client.get(f"/api/pages/{page_id}")
    assert page_detail_response.status_code == 200
    assert page_detail_response.json()["id"] == page_id
    assert page_detail_response.json()["page_content"] == "demo-page"
    assert page_detail_response.json()["speaker_notes"] == "开场介绍本页目标。"
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

async def test_page_speaker_notes_update_should_create_page_version(authenticated_client: AsyncClient) -> None:
    """仅修改演讲者备注时也应生成页面版本，供演讲模式回溯备注。"""

    workspace = await _create_catalog_workspace(authenticated_client, "备注版本页面空间")
    project = await _create_catalog_project(authenticated_client, workspace["id"], "备注版本页面项目")
    page = await _create_catalog_page(
        authenticated_client,
        workspace["id"],
        project["id"],
        "备注版本页面",
        page_content="<template><div>notes</div></template>",
        speaker_notes="初始备注",
    )

    update_response = await authenticated_client.patch(
        f"/api/pages/{page['id']}",
        json={"speaker_notes": "只更新备注", "change_note": "更新演讲者备注"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 2
    assert update_response.json()["page_content"] == "<template><div>notes</div></template>"
    assert update_response.json()["speaker_notes"] == "只更新备注"

    version_1_response = await authenticated_client.get(f"/api/pages/{page['id']}/versions/1")
    assert version_1_response.status_code == 200
    assert version_1_response.json()["resolved_content"] == "<template><div>notes</div></template>"
    assert version_1_response.json()["speaker_notes"] == "初始备注"
