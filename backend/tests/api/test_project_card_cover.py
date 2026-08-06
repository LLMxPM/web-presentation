"""文件功能：验证项目卡片封面页按路由优先、页面编码兜底的规则选择。"""

from httpx import AsyncClient


async def _create_page(client: AsyncClient, workspace_id: int, project_id: int, title: str) -> dict:
    """创建封面选择测试页面并返回接口响应。"""

    response = await client.post(
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
    assert response.status_code == 200
    return response.json()


async def test_project_card_cover_should_prefer_first_route_then_fallback_to_page_code(
    authenticated_client: AsyncClient,
) -> None:
    """项目封面应优先使用首个可见路由页，无路由时回退到编码最小的页面。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "卡片封面空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "卡片封面项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    code_first_page = await _create_page(authenticated_client, workspace_id, project_id, "编码靠前页")
    route_first_page = await _create_page(authenticated_client, workspace_id, project_id, "路由首页")

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 10,
                    "hidden": False,
                    "page_id": route_first_page["id"],
                    "children": [],
                },
                {
                    "route_type": "page",
                    "route": "appendix",
                    "order": 20,
                    "hidden": False,
                    "page_id": code_first_page["id"],
                    "children": [],
                },
            ]
        },
    )
    assert route_response.status_code == 200

    list_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active"
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["first_page_title"] == "路由首页"

    clear_routes_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={"routes": []},
    )
    assert clear_routes_response.status_code == 200

    fallback_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active"
    )
    assert fallback_response.status_code == 200
    assert fallback_response.json()["items"][0]["first_page_title"] == "编码靠前页"
