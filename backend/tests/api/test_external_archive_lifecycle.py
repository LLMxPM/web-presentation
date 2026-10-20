"""文件功能：验证 CLI 使用的 External API 归档保留数据、支持 Editor 恢复且整批原子执行。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.enums import ProjectRouteType, RecordStatus
from app.models.page import Page
from app.models.project_route import ProjectRoute
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.page_version_service import PageVersionService


@pytest.fixture
async def archive_targets(authenticated_client: AsyncClient) -> tuple[dict[str, str], list[int], list[int]]:
    """在独立测试库中创建两个带页面、版本和分组路由的项目，并签发归档 PAT。"""

    async with get_session_factory()() as session:
        user_id = await session.scalar(select(User.id).where(User.username == "admin"))
        workspace = Workspace(code="archive-ws", name="归档测试", created_by=user_id, updated_by=user_id)
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner", status="active"))
        project_ids, page_ids = [], []
        for index in range(2):
            project = Project(
                workspace_id=workspace.id,
                code=f"archive-project-{index}",
                name=f"归档项目 {index}",
                theme_config_yaml="{}",
                created_by=user_id,
                updated_by=user_id,
            )
            session.add(project)
            await session.flush()
            page = Page(
                workspace_id=workspace.id,
                project_id=project.id,
                code=f"archive-page-{index}",
                title=f"归档页面 {index}",
                page_content=f"<template><div>页面 {index}</div></template>",
                speaker_notes=f"演讲备注 {index}",
                created_by=user_id,
                updated_by=user_id,
            )
            session.add(page)
            await session.flush()
            await PageVersionService(session).initialize_page_version(page, user_id)
            group = ProjectRoute(
                project_id=project.id, route="/group", order=0,
                route_type=ProjectRouteType.GROUP.value, group_title="章节",
            )
            session.add(group)
            await session.flush()
            session.add(ProjectRoute(
                project_id=project.id, parent_id=group.id, route="page", order=0,
                page_id=page.id, route_type=ProjectRouteType.PAGE.value,
            ))
            project_ids.append(project.id)
            page_ids.append(page.id)
        token = await ApiAccessTokenService(session).create_token(
            user_id=user_id,
            payload=ApiAccessTokenCreateRequest(
                name="归档测试 PAT", workspace_ids=[workspace.id],
                scopes=["project:read", "project:write", "page:read", "page:write"],
            ),
        )
        headers = {"Authorization": f"Bearer {token.token}", "X-Workspace-ID": str(workspace.id)}
        await session.commit()
        return headers, project_ids, page_ids


@pytest.mark.parametrize("entity_type", ["page", "project"])
@pytest.mark.parametrize("batch", [False, True], ids=["single", "batch"])
async def test_external_archive_preserves_data_and_editor_can_restore(
    authenticated_client: AsyncClient,
    archive_targets: tuple[dict[str, str], list[int], list[int]],
    entity_type: str,
    batch: bool,
) -> None:
    """归档及幂等重放后数据仍可查询与恢复；页面移除路由，项目归档不级联。"""

    client = authenticated_client
    headers, project_ids, page_ids = archive_targets
    all_ids = page_ids if entity_type == "page" else project_ids
    target_ids = all_ids if batch else all_ids[:1]
    archive_headers = {**headers, "Idempotency-Key": f"archive-{entity_type}-{batch}"}
    path = f"/api/v1/{entity_type}s/" + ("batch-archive" if batch else f"{target_ids[0]}/archive")
    response = await client.post(path, headers=archive_headers, json={"ids": target_ids} if batch else None)
    assert response.status_code == 200, response.text
    if batch:
        assert response.json() == {"archived_ids": target_ids, "failed_ids": [], "total": len(target_ids)}
    replay = await client.post(path, headers=archive_headers, json={"ids": target_ids} if batch else None)
    assert replay.status_code == 200, replay.text
    assert replay.json() == response.json()

    async with get_session_factory()() as session:
        model = Page if entity_type == "page" else Project
        for target_id in target_ids:
            target = await session.get(model, target_id)
            assert target.status == RecordStatus.ARCHIVED.value
            assert target.deleted_at is None
            if entity_type == "project":
                assert target.archived_at is not None
        for index, page_id in enumerate(page_ids):
            page = await session.get(Page, page_id)
            assert page.deleted_at is None
            assert page.page_content == f"<template><div>页面 {index}</div></template>"
            assert page.speaker_notes == f"演讲备注 {index}"
            assert page.current_version_no == 1
            expected_routes = 0 if entity_type == "page" and page_id in target_ids else 2
            routes = list((await session.scalars(select(ProjectRoute).where(
                ProjectRoute.project_id == project_ids[index],
            ))).all())
            assert len(routes) == expected_routes
            if entity_type == "project":
                assert page.status == RecordStatus.ACTIVE.value

    list_path = f"/api/{entity_type}s"
    archived = await client.get(list_path, params={"workspace_id": headers["X-Workspace-ID"], "status": "archived"})
    assert archived.status_code == 200, archived.text
    assert {item["id"] for item in archived.json()["items"]} == set(target_ids)
    active = await client.get(list_path, params={"workspace_id": headers["X-Workspace-ID"], "status": "active"})
    assert active.status_code == 200, active.text
    assert {item["id"] for item in active.json()["items"]} == set(all_ids) - set(target_ids)

    for page_id in page_ids:
        versions = await client.get(f"/api/v1/pages/{page_id}/versions", headers=headers)
        assert versions.status_code == 200, versions.text
        assert [item["version_no"] for item in versions.json()] == [1]
        source = await client.get(f"/api/v1/pages/{page_id}/source", headers=headers)
        assert source.status_code == 200, source.text
    for target_id in target_ids:
        detail = await client.get(f"/api/v1/{entity_type}s/{target_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["status"] == "archived"
        restored = await client.patch(f"/api/{entity_type}s/{target_id}", json={"status": "active"})
        assert restored.status_code == 200, restored.text
        assert restored.json()["status"] == "active"


@pytest.mark.parametrize("entity_type", ["page", "project"])
async def test_external_batch_archive_failure_rolls_back_all_changes(
    authenticated_client: AsyncClient,
    archive_targets: tuple[dict[str, str], list[int], list[int]],
    entity_type: str,
) -> None:
    """后续目标不存在时，前面目标的归档状态、删除标记和路由变更全部回滚。"""

    headers, project_ids, page_ids = archive_targets
    target_ids = page_ids if entity_type == "page" else project_ids
    response = await authenticated_client.post(
        f"/api/v1/{entity_type}s/batch-archive",
        headers={**headers, "Idempotency-Key": f"archive-rollback-{entity_type}"},
        json={"ids": [target_ids[0], max(target_ids) + 1000]},
    )
    assert response.status_code == 404, response.text
    async with get_session_factory()() as session:
        for model, ids in ((Page, page_ids), (Project, project_ids)):
            for target_id in ids:
                target = await session.get(model, target_id)
                assert target.status == RecordStatus.ACTIVE.value
                assert target.deleted_at is None
                if model is Project:
                    assert target.archived_at is None
        routes = list((await session.scalars(select(ProjectRoute))).all())
        assert len(routes) == 4
