"""文件功能：验证样式建议组件与项目建议组件快照接口的保存、校验和复制行为。"""

from httpx import AsyncClient


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_style(authenticated_client: AsyncClient, workspace_id: int, key: str, name: str) -> int:
    """创建工作空间样式并返回主键。"""

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/styles",
        json={
            "key": key,
            "name": name,
            "page_width": 1920,
            "page_height": 1080,
            "base_font_size": "20px",
            "icon_default_stroke_width": 2,
            "show_pdf_export_button": True,
            "menu_mode": "preview",
            "theme_key": None,
            "style_spec_markdown": "## 组件\n优先复用建议组件。",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str, **extra: object) -> int:
    """创建测试项目并返回主键。"""

    payload = {"workspace_id": workspace_id, "name": name, "status": "active", **extra}
    response = await authenticated_client.post("/api/projects", json=payload)
    assert response.status_code == 200
    return response.json()["id"]


async def _create_component(
    authenticated_client: AsyncClient,
    workspace_id: int,
    name: str,
    import_name: str,
    *,
    publish: bool = True,
) -> dict:
    """创建工作空间组件，并按需发布后返回接口载荷。"""

    response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": name,
            "import_name": import_name,
            "content": f"<template><section>{name}</section></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200
    component = response.json()
    if not publish:
        return component
    publish_response = await authenticated_client.post(
        f"/api/components/{component['id']}/publish",
        json={"release_name": None, "change_note": "测试发布"},
    )
    assert publish_response.status_code == 200
    return publish_response.json()


async def test_workspace_style_suggested_components_should_save_published_components_in_order(
    authenticated_client: AsyncClient,
) -> None:
    """样式建议组件应只返回精简字段，并按用户选择顺序去重保存。"""

    workspace_id = await _create_workspace(authenticated_client, "样式建议组件空间")
    style_id = await _create_style(authenticated_client, workspace_id, "sales", "销售样式")
    card_component = await _create_component(authenticated_client, workspace_id, "指标卡片", "MetricCard")
    chart_component = await _create_component(authenticated_client, workspace_id, "趋势图表", "TrendChart")

    save_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components",
        json={"component_ids": [chart_component["id"], card_component["id"], chart_component["id"]]},
    )

    assert save_response.status_code == 200
    items = save_response.json()["items"]
    assert [item["id"] for item in items] == [chart_component["id"], card_component["id"]]
    assert set(items[0]) == {
        "id",
        "code",
        "name",
        "import_name",
        "component_type",
        "summary",
        "current_version_no",
        "available",
        "unavailable_reason",
    }
    assert "content" not in items[0]
    assert items[0]["current_version_no"] == 1
    assert items[0]["available"] is True
    assert items[0]["unavailable_reason"] is None

    get_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components"
    )
    assert get_response.status_code == 200
    assert [item["id"] for item in get_response.json()["items"]] == [chart_component["id"], card_component["id"]]


async def test_suggested_components_should_reject_invalid_or_unpublished_components(
    authenticated_client: AsyncClient,
) -> None:
    """建议组件应拒绝跨工作空间、未发布、归档或不存在组件。"""

    workspace_id = await _create_workspace(authenticated_client, "建议组件校验空间")
    other_workspace_id = await _create_workspace(authenticated_client, "其他建议组件空间")
    style_id = await _create_style(authenticated_client, workspace_id, "strict", "严格样式")
    project_id = await _create_project(authenticated_client, workspace_id, "建议组件校验项目")
    unpublished_component = await _create_component(authenticated_client, workspace_id, "草稿组件", "DraftBlock", publish=False)
    other_component = await _create_component(authenticated_client, other_workspace_id, "外部组件", "OtherBlock")
    archived_component = await _create_component(authenticated_client, workspace_id, "归档组件", "ArchivedBlock")
    archive_response = await authenticated_client.patch(
        f"/api/components/{archived_component['id']}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200

    for component_id in (unpublished_component["id"], other_component["id"], archived_component["id"], 999999):
        style_response = await authenticated_client.put(
            f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components",
            json={"component_ids": [component_id]},
        )
        assert style_response.status_code == 400
        assert style_response.json()["code"] == "WORKSPACE_STYLE_SUGGESTED_COMPONENT_INVALID"

        project_response = await authenticated_client.put(
            f"/api/projects/{project_id}/suggested-components",
            json={"component_ids": [component_id]},
        )
        assert project_response.status_code == 400
        assert project_response.json()["code"] == "PROJECT_SUGGESTED_COMPONENT_INVALID"


async def test_suggested_components_should_keep_unavailable_items_for_cleanup(
    authenticated_client: AsyncClient,
) -> None:
    """管理接口应显示已失效建议组件，并提示用户移除后保存。"""

    workspace_id = await _create_workspace(authenticated_client, "建议组件清理空间")
    style_id = await _create_style(authenticated_client, workspace_id, "cleanup", "清理样式")
    project_id = await _create_project(authenticated_client, workspace_id, "建议组件清理项目")
    deleted_component = await _create_component(authenticated_client, workspace_id, "旧组件", "LegacyBlock")
    active_component = await _create_component(authenticated_client, workspace_id, "新组件", "FreshBlock")

    style_save_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components",
        json={"component_ids": [deleted_component["id"], active_component["id"]]},
    )
    assert style_save_response.status_code == 200
    project_save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-components",
        json={"component_ids": [deleted_component["id"], active_component["id"]]},
    )
    assert project_save_response.status_code == 200

    delete_response = await authenticated_client.delete(f"/api/components/{deleted_component['id']}")
    assert delete_response.status_code == 200

    style_get_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components"
    )
    assert style_get_response.status_code == 200
    style_items = style_get_response.json()["items"]
    assert [item["id"] for item in style_items] == [deleted_component["id"], active_component["id"]]
    assert style_items[0]["available"] is False
    assert style_items[0]["unavailable_reason"] == "组件已删除，请移除后保存。"
    assert style_items[1]["available"] is True

    project_get_response = await authenticated_client.get(f"/api/projects/{project_id}/suggested-components")
    assert project_get_response.status_code == 200
    project_items = project_get_response.json()["items"]
    assert [item["id"] for item in project_items] == [deleted_component["id"], active_component["id"]]
    assert project_items[0]["available"] is False
    assert project_items[0]["unavailable_reason"] == "组件已删除，请移除后保存。"

    cleanup_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components",
        json={"component_ids": [active_component["id"]]},
    )
    assert cleanup_response.status_code == 200
    assert [item["id"] for item in cleanup_response.json()["items"]] == [active_component["id"]]


async def test_style_copy_and_project_apply_should_copy_suggested_component_snapshots(
    authenticated_client: AsyncClient,
) -> None:
    """样式复制和项目应用样式时应复制建议组件，项目迁移工作空间时应清空快照。"""

    workspace_id = await _create_workspace(authenticated_client, "建议组件复制空间")
    target_workspace_id = await _create_workspace(authenticated_client, "建议组件迁移空间")
    style_id = await _create_style(authenticated_client, workspace_id, "deck", "路演样式")
    another_style_id = await _create_style(authenticated_client, workspace_id, "report", "报告样式")
    hero_component = await _create_component(authenticated_client, workspace_id, "头图组件", "HeroBlock")
    table_component = await _create_component(authenticated_client, workspace_id, "表格组件", "DataTableBlock")
    await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/suggested-components",
        json={"component_ids": [hero_component["id"]]},
    )
    await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/styles/{another_style_id}/suggested-components",
        json={"component_ids": [table_component["id"]]},
    )

    copy_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/styles/{style_id}/copy",
        json={"key": "deck-copy", "name": "路演样式副本"},
    )
    assert copy_response.status_code == 200
    copied_style_id = copy_response.json()["id"]
    copied_components_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/styles/{copied_style_id}/suggested-components"
    )
    assert [item["id"] for item in copied_components_response.json()["items"]] == [hero_component["id"]]

    project_id = await _create_project(
        authenticated_client,
        workspace_id,
        "应用建议组件项目",
        suggested_component_source_style_id=style_id,
    )
    project_components_response = await authenticated_client.get(f"/api/projects/{project_id}/suggested-components")
    assert [item["id"] for item in project_components_response.json()["items"]] == [hero_component["id"]]

    update_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"suggested_component_source_style_id": another_style_id},
    )
    assert update_response.status_code == 200
    replaced_components_response = await authenticated_client.get(f"/api/projects/{project_id}/suggested-components")
    assert [item["id"] for item in replaced_components_response.json()["items"]] == [table_component["id"]]

    move_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"workspace_id": target_workspace_id},
    )
    assert move_response.status_code == 200
    cleared_response = await authenticated_client.get(f"/api/projects/{project_id}/suggested-components")
    assert cleared_response.status_code == 200
    assert cleared_response.json()["items"] == []
