"""文件功能：验证逐页放映覆盖的写入、继承生效值、旧客户端保留、整树事务与重复引用独立性。"""

from __future__ import annotations

from httpx import AsyncClient

PROJECT_SLIDESHOW = {
    "transition": {"effect": "fade", "duration_ms": 400},
    "advance": {"mode": "timer", "delay_ms": 7000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    "loop": False,
    "auto_start": False,
}


async def _create_workspace(client: AsyncClient, name: str) -> int:
    """创建工作空间并返回 ID。"""

    response = await client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project_with_pages(client: AsyncClient, workspace_id: int, page_titles: list[str]) -> tuple[int, list[int]]:
    """创建启用放映配置的项目及若干 Vue 页面。"""

    project_response = await client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "路由放映项目",
            "status": "active",
            "slideshow": PROJECT_SLIDESHOW,
        },
    )
    assert project_response.status_code == 200, project_response.text
    project_id = project_response.json()["id"]

    page_ids: list[int] = []
    for title in page_titles:
        page_response = await client.post(
            "/api/pages",
            json={
                "page_content": f"<template><div>{title}</div></template>",
                "file_type": "vue",
                "title": title,
                "status": "active",
                "workspace_id": workspace_id,
                "project_id": project_id,
            },
        )
        assert page_response.status_code == 200, page_response.text
        page_ids.append(page_response.json()["id"])
    return project_id, page_ids


async def _put_tree(client: AsyncClient, project_id: int, routes: list[dict]) -> object:
    """提交整树路由配置。"""

    return await client.put(f"/api/projects/{project_id}/routes", json={"routes": routes})


async def _get_tree(client: AsyncClient, project_id: int) -> dict:
    """读取路由树响应。"""

    response = await client.get(f"/api/projects/{project_id}/routes")
    assert response.status_code == 200, response.text
    return response.json()


def _find_route(tree: dict, route: str) -> dict:
    """在两层路由树中按路由名查找节点。"""

    for item in tree["routes"]:
        if item["route"] == route:
            return item
        for child in item.get("children", []):
            if child["route"] == route:
                return child
    raise AssertionError(f"路由不存在：{route}")


async def test_route_overrides_should_return_raw_and_effective_values(authenticated_client: AsyncClient) -> None:
    """叶子覆盖按整组保存，响应同时返回原始覆盖与按组回退的生效值。"""

    workspace_id = await _create_workspace(authenticated_client, "路由覆盖空间")
    project_id, page_ids = await _create_project_with_pages(authenticated_client, workspace_id, ["概览页", "引导页", "细节页"])

    response = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "overview",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "transition": {"effect": "push", "duration_ms": 600},
                "advance": {"mode": "timer", "delay_ms": 8000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                "children": [],
            },
            {
                "route_type": "group",
                "route": "chapter",
                "order": 2,
                "hidden": False,
                "group_title": "章节",
                "children": [
                    {
                        "route": "intro",
                        "order": 1,
                        "hidden": False,
                        "page_id": page_ids[1],
                    },
                    {
                        "route": "detail",
                        "order": 2,
                        "hidden": False,
                        "page_id": page_ids[2],
                        "advance": {"mode": "manual", "delay_ms": 3000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                    },
                ],
            },
        ],
    )
    assert response.status_code == 200, response.text

    tree = await _get_tree(authenticated_client, project_id)

    overview = _find_route(tree, "overview")
    assert overview["transition"] == {"effect": "push", "duration_ms": 600}
    assert overview["advance"] == {"mode": "timer", "delay_ms": 8000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert overview["effective_slideshow"] == {
        "transition": {"effect": "push", "duration_ms": 600},
        "advance": {"mode": "timer", "delay_ms": 8000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    }

    intro = _find_route(tree, "intro")
    assert intro["transition"] is None
    assert intro["advance"] is None
    assert intro["effective_slideshow"] == {
        "transition": {"effect": "fade", "duration_ms": 400},
        "advance": {"mode": "timer", "delay_ms": 7000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    }

    detail = _find_route(tree, "detail")
    assert detail["transition"] is None
    assert detail["advance"] == {"mode": "manual", "delay_ms": 3000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert detail["effective_slideshow"] == {
        "transition": {"effect": "fade", "duration_ms": 400},
        "advance": {"mode": "manual", "delay_ms": 3000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
    }

    group = _find_route(tree, "chapter")
    assert group["transition"] is None
    assert group["advance"] is None
    assert group["effective_slideshow"] is None


async def test_legacy_client_reorder_should_preserve_overrides(authenticated_client: AsyncClient) -> None:
    """旧客户端整树 PUT 省略新字段时，按完整路径与页面绑定保留已匹配节点的覆盖。"""

    workspace_id = await _create_workspace(authenticated_client, "旧客户端空间")
    project_id, page_ids = await _create_project_with_pages(authenticated_client, workspace_id, ["首页", "次页"])

    first_write = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "home",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "transition": {"effect": "push", "duration_ms": 700},
                "advance": {"mode": "timer", "delay_ms": 6000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                "children": [],
            },
            {
                "route_type": "page",
                "route": "second",
                "order": 2,
                "hidden": False,
                "page_id": page_ids[1],
                "children": [],
            },
        ],
    )
    assert first_write.status_code == 200, first_write.text

    # 旧客户端只调整排序，不携带新增字段。
    legacy_write = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "home",
                "order": 2,
                "hidden": False,
                "page_id": page_ids[0],
                "children": [],
            },
            {
                "route_type": "page",
                "route": "second",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[1],
                "children": [],
            },
        ],
    )
    assert legacy_write.status_code == 200, legacy_write.text

    tree = await _get_tree(authenticated_client, project_id)
    home = _find_route(tree, "home")
    assert home["transition"] == {"effect": "push", "duration_ms": 700}
    assert home["advance"] == {"mode": "timer", "delay_ms": 6000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}

    # 新节点省略字段时继承项目默认值。
    added = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "home",
                "order": 2,
                "hidden": False,
                "page_id": page_ids[0],
                "children": [],
            },
            {
                "route_type": "page",
                "route": "brand-new",
                "order": 3,
                "hidden": False,
                "page_id": page_ids[1],
                "children": [],
            },
        ],
    )
    assert added.status_code == 200, added.text
    tree = await _get_tree(authenticated_client, project_id)
    assert _find_route(tree, "home")["transition"] == {"effect": "push", "duration_ms": 700}
    new_route = _find_route(tree, "brand-new")
    assert new_route["transition"] is None
    assert new_route["effective_slideshow"]["transition"] == {"effect": "fade", "duration_ms": 400}


async def test_explicit_null_should_clear_single_override_group(authenticated_client: AsyncClient) -> None:
    """显式 null 只清除对应组的覆盖，另一组覆盖保持。"""

    workspace_id = await _create_workspace(authenticated_client, "清除覆盖空间")
    project_id, page_ids = await _create_project_with_pages(authenticated_client, workspace_id, ["清除页"])

    initial = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "clear",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "transition": {"effect": "none", "duration_ms": 0},
                "advance": {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                "children": [],
            },
        ],
    )
    assert initial.status_code == 200, initial.text

    cleared = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "clear",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "transition": None,
                "advance": {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                "children": [],
            },
        ],
    )
    assert cleared.status_code == 200, cleared.text

    tree = await _get_tree(authenticated_client, project_id)
    node = _find_route(tree, "clear")
    assert node["transition"] is None
    assert node["advance"] == {"mode": "manual", "delay_ms": 2000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
    assert node["effective_slideshow"]["transition"] == {"effect": "fade", "duration_ms": 400}


async def test_group_override_or_invalid_group_should_reject_whole_tree(authenticated_client: AsyncClient) -> None:
    """分组承载覆盖或节点参数非法时整树 422，且旧路由与覆盖保持原样。"""

    workspace_id = await _create_workspace(authenticated_client, "整树拒绝空间")
    project_id, page_ids = await _create_project_with_pages(authenticated_client, workspace_id, ["拒绝页", "分组页"])

    initial = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "keep",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "transition": {"effect": "push", "duration_ms": 500},
                "advance": {"mode": "timer", "delay_ms": 4000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                "children": [],
            },
        ],
    )
    assert initial.status_code == 200, initial.text

    group_with_override = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "group",
                "route": "chapter",
                "order": 1,
                "hidden": False,
                "group_title": "章节",
                "transition": {"effect": "fade", "duration_ms": 400},
                "children": [{"route": "child", "order": 1, "hidden": False, "page_id": page_ids[1]}],
            },
        ],
    )
    assert group_with_override.status_code == 422

    partial_override = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "keep",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "advance": {"mode": "timer"},
                "children": [],
            },
        ],
    )
    assert partial_override.status_code == 422

    tree = await _get_tree(authenticated_client, project_id)
    assert len(tree["routes"]) == 1
    node = _find_route(tree, "keep")
    assert node["transition"] == {"effect": "push", "duration_ms": 500}
    assert node["advance"] == {"mode": "timer", "delay_ms": 4000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}


async def test_same_page_referenced_twice_should_keep_independent_overrides(authenticated_client: AsyncClient) -> None:
    """同一页面被多个路由引用时，各路由的放映设置互不影响。"""

    workspace_id = await _create_workspace(authenticated_client, "重复引用空间")
    project_id, page_ids = await _create_project_with_pages(authenticated_client, workspace_id, ["共享页"])

    response = await _put_tree(
        authenticated_client,
        project_id,
        [
            {
                "route_type": "page",
                "route": "first",
                "order": 1,
                "hidden": False,
                "page_id": page_ids[0],
                "transition": {"effect": "push", "duration_ms": 600},
                "children": [],
            },
            {
                "route_type": "page",
                "route": "second",
                "order": 2,
                "hidden": False,
                "page_id": page_ids[0],
                "advance": {"mode": "manual", "delay_ms": 1000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000},
                "children": [],
            },
        ],
    )
    assert response.status_code == 200, response.text

    tree = await _get_tree(authenticated_client, project_id)
    first = _find_route(tree, "first")
    second = _find_route(tree, "second")
    assert first["transition"] == {"effect": "push", "duration_ms": 600}
    assert first["advance"] is None
    assert second["transition"] is None
    assert second["advance"] == {"mode": "manual", "delay_ms": 1000, "media_timeout_ms": 300000, "timeline_timeout_ms": 300000}
