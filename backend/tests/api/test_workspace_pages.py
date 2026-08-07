"""文件功能：验证工作空间全部页面列表的分页、搜索和项目归属过滤。"""

from httpx import AsyncClient


async def test_workspace_page_list_should_support_assigned_filter_pagination_and_keyword(
    authenticated_client: AsyncClient,
) -> None:
    """工作空间页面列表应只返回启用项目页面，并支持服务端分页搜索。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "工作空间页面列表测试", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "页面列表项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    assigned_titles = ["页面列表甲", "页面列表乙"]
    assigned_pages = []
    for title in assigned_titles:
        response = await authenticated_client.post(
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
        assigned_pages.append(response.json())

    unassigned_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>未归属页面</div></template>",
            "file_type": "vue",
            "title": "未归属页面",
            "status": "active",
            "workspace_id": workspace_id,
        },
    )
    assert unassigned_response.status_code == 200

    first_page_response = await authenticated_client.get(
        f"/api/pages?workspace_id={workspace_id}&project_assigned=true&status=active&page=1&page_size=1",
    )
    assert first_page_response.status_code == 200
    assert first_page_response.json()["total"] == 2
    assert len(first_page_response.json()["items"]) == 1
    assert first_page_response.json()["items"][0]["project_id"] == project_id

    search_response = await authenticated_client.get(
        f"/api/pages?workspace_id={workspace_id}&project_assigned=true&status=active&keyword={assigned_titles[1]}",
    )
    assert search_response.status_code == 200
    assert [item["title"] for item in search_response.json()["items"]] == [assigned_titles[1]]

    archive_response = await authenticated_client.patch(
        f"/api/pages/{assigned_pages[0]['id']}",
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200

    after_archive_response = await authenticated_client.get(
        f"/api/pages?workspace_id={workspace_id}&project_assigned=true&status=active&page=1&page_size=10",
    )
    assert after_archive_response.status_code == 200
    assert after_archive_response.json()["total"] == 1
    assert after_archive_response.json()["items"][0]["title"] == assigned_titles[1]

    archive_project_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"status": "archived"},
    )
    assert archive_project_response.status_code == 200

    after_project_archive_response = await authenticated_client.get(
        f"/api/pages?workspace_id={workspace_id}&project_assigned=true&status=active&page=1&page_size=10",
    )
    assert after_project_archive_response.status_code == 200
    assert after_project_archive_response.json()["total"] == 0
    assert after_project_archive_response.json()["items"] == []
