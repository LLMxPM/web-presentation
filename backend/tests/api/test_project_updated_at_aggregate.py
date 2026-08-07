"""文件功能：验证项目 updated_at 取项目自身与关联未软删除页面最新更新时间的最大值。"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.page import Page
from app.models.workspace import Project


async def _create_workspace_project(client: AsyncClient, workspace_name: str, project_name: str) -> tuple[int, int]:
    """创建工作空间与项目，返回 workspace_id 与 project_id。"""

    workspace_response = await client.post("/api/workspaces", json={"name": workspace_name, "status": "active"})
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    return workspace_id, await _create_project(client, workspace_id, project_name)


async def _create_project(client: AsyncClient, workspace_id: int, project_name: str) -> int:
    """在指定工作空间下创建项目并返回项目 id。"""

    project_response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": project_name, "status": "active"},
    )
    assert project_response.status_code == 200
    return project_response.json()["id"]


async def _create_page(client: AsyncClient, workspace_id: int, project_id: int, title: str) -> int:
    """创建关联页面并返回页面 id。"""

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
    return response.json()["id"]


async def _set_updated_at(model: type, entity_id: int, updated_at: datetime) -> None:
    """直接写库覆盖指定记录的 updated_at，用于构造可控的排序场景。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        from sqlalchemy import update

        result = await session.execute(
            update(model)
            .where(model.id == entity_id)
            .values(updated_at=updated_at)
        )
        assert (result.rowcount or 0) == 1
        await session.commit()


async def test_project_updated_at_should_be_max_of_project_and_pages(
    authenticated_client: AsyncClient,
) -> None:
    """项目 updated_at 应取项目自身与关联页面最新更新时间的最大值。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "更新时间空间", "聚合项目")
    page_id = await _create_page(authenticated_client, workspace_id, project_id, "聚合页面")

    base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    project_updated_at = base + timedelta(days=1)
    page_updated_at = base + timedelta(days=2)
    await _set_updated_at(Project, project_id, project_updated_at)
    await _set_updated_at(Page, page_id, page_updated_at)

    list_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active",
    )
    assert list_response.status_code == 200
    project_item = next(item for item in list_response.json()["items"] if item["id"] == project_id)
    assert project_item["updated_at"].startswith("2026-08-03T00:00:00")

    detail_response = await authenticated_client.get(f"/api/projects/{project_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["updated_at"].startswith("2026-08-03T00:00:00")


async def test_project_updated_at_should_fall_back_to_project_when_no_page_is_newer(
    authenticated_client: AsyncClient,
) -> None:
    """当项目自身更新时间晚于所有页面时，updated_at 应保持项目自身时间。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "回退空间", "回退项目")
    page_id = await _create_page(authenticated_client, workspace_id, project_id, "回退页面")

    base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    project_updated_at = base + timedelta(days=3)
    page_updated_at = base + timedelta(days=1)
    await _set_updated_at(Project, project_id, project_updated_at)
    await _set_updated_at(Page, page_id, page_updated_at)

    list_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active",
    )
    assert list_response.status_code == 200
    project_item = next(item for item in list_response.json()["items"] if item["id"] == project_id)
    assert project_item["updated_at"].startswith("2026-08-04T00:00:00")


async def test_project_updated_at_should_ignore_soft_deleted_pages(
    authenticated_client: AsyncClient,
) -> None:
    """软删除页面不应参与项目更新时间聚合。"""

    workspace_id, project_id = await _create_workspace_project(authenticated_client, "软删空间", "软删项目")
    page_id = await _create_page(authenticated_client, workspace_id, project_id, "软删页面")

    base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    project_updated_at = base + timedelta(days=1)
    page_updated_at = base + timedelta(days=2)

    session_factory = get_session_factory()
    async with session_factory() as session:
        from sqlalchemy import update

        await session.execute(
            update(Page)
            .where(Page.id == page_id)
            .values(updated_at=page_updated_at, deleted_at=page_updated_at)
        )
        await session.commit()
    await _set_updated_at(Project, project_id, project_updated_at)

    list_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active",
    )
    assert list_response.status_code == 200
    project_item = next(item for item in list_response.json()["items"] if item["id"] == project_id)
    assert project_item["updated_at"].startswith("2026-08-02T00:00:00")


async def test_project_list_should_sort_by_max_project_and_page_updated_at(
    authenticated_client: AsyncClient,
) -> None:
    """项目列表默认排序应基于项目与页面更新时间的最大值。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "排序空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    first_project_id = await _create_project(authenticated_client, workspace_id, "排序项目一")
    second_project_id = await _create_project(authenticated_client, workspace_id, "排序项目二")
    first_page_id = await _create_page(authenticated_client, workspace_id, first_project_id, "排序页面一")

    base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    first_project_updated_at = base + timedelta(days=1)
    first_page_updated_at = base + timedelta(days=3)
    second_project_updated_at = base + timedelta(days=2)
    await _set_updated_at(Project, first_project_id, first_project_updated_at)
    await _set_updated_at(Page, first_page_id, first_page_updated_at)
    await _set_updated_at(Project, second_project_id, second_project_updated_at)

    list_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active",
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert [item["id"] for item in items] == [first_project_id, second_project_id]


async def test_project_list_should_keep_asc_order_on_aggregate_updated_at(
    authenticated_client: AsyncClient,
) -> None:
    """升序排序同样基于项目与页面更新时间的最大值。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "升序空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    first_project_id = await _create_project(authenticated_client, workspace_id, "升序项目一")
    second_project_id = await _create_project(authenticated_client, workspace_id, "升序项目二")
    first_page_id = await _create_page(authenticated_client, workspace_id, first_project_id, "升序页面一")

    base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    first_project_updated_at = base + timedelta(days=1)
    first_page_updated_at = base + timedelta(days=3)
    second_project_updated_at = base + timedelta(days=2)
    await _set_updated_at(Project, first_project_id, first_project_updated_at)
    await _set_updated_at(Page, first_page_id, first_page_updated_at)
    await _set_updated_at(Project, second_project_id, second_project_updated_at)

    list_response = await authenticated_client.get(
        f"/api/projects?page=1&page_size=10&workspace_id={workspace_id}&status=active&sort_order=asc",
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert [item["id"] for item in items] == [second_project_id, first_project_id]
