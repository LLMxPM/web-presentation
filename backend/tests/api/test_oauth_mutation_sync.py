"""文件功能：验证委托页面/组件轻元数据、组件发布和单项归档继续同步且发布幂等。"""

from datetime import timedelta

import pytest
from app.core.time_utils import utc_now
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.api_mutation_job import ApiMutationJob
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from sqlalchemy import func, select, update

from tests.fixtures.oauth_mutations import SOURCE, delegate_headers, other_user_access


async def test_light_metadata_publish_and_single_archive_remain_synchronous(
    oauth_mutation_client,
):
    """真实委托同步写入不创建 Mutation；发布重放仅生成一个正式组件版本。"""
    client, factory, access, pat = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"], key="sync")
    page = await client.patch(
        "/api/v1/pages/1",
        json={"title": "已改标题", "summary": "摘要"},
        headers=headers,
    )
    assert page.status_code == 200 and page.json()["title"] == "已改标题"
    component = await client.patch(
        "/api/v1/components/1",
        json={"name": "已改名称", "summary": "摘要"},
        headers=headers,
    )
    assert component.status_code == 200 and component.json()["name"] == "已改名称"
    publish = await client.post(
        "/api/v1/components/1/publish", json={}, headers=headers
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["current_version_no"] == 1
    replay = await client.post(
        "/api/v1/components/1/publish",
        json={},
        headers={**headers, "Authorization": "Bearer " + pat},
    )
    assert replay.status_code == 200 and replay.json() == publish.json()
    for entity in ("pages", "components"):
        response = await client.post(f"/api/v1/{entity}/1/archive", headers=headers)
        assert response.status_code == 200, response.text
        replay = await client.post(f"/api/v1/{entity}/1/archive", headers=headers)
        assert replay.status_code == 200 and replay.json() == response.json(), (
            replay.text
        )
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(WorkspaceComponentVersion)
            )
            == 1
        )
        page = await session.get(Page, 1)
        component = await session.get(WorkspaceComponent, 1)
        assert page.deleted_at is not None and component.status == "archived"
        assert page.page_content == component.content == SOURCE
        assert page.current_version_no == component.current_version_no == 1


@pytest.mark.parametrize("entity", ["pages", "components"])
async def test_archive_replay_still_requires_current_permissions(
    oauth_mutation_client,
    entity,
):
    """允许原键重放不公开已删除页面；新键、跨用户和撤销后的旧凭证不能复用旧结果。"""
    client, factory, access, pat = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"], key="archive")
    path = f"/api/v1/{entity}/1/archive"
    first = await client.post(path, headers=headers)
    assert first.status_code == 200, first.text
    replay = await client.post(
        path, headers={**headers, "Authorization": "Bearer " + pat}
    )
    assert replay.status_code == 200 and replay.json() == first.json()
    new_key = await client.post(
        path, headers={**headers, "Idempotency-Key": "new-archive"}
    )
    assert new_key.status_code == 404
    assert (await client.get(f"/api/v1/{entity}/1", headers=headers)).status_code == 404
    other = await other_user_access(client, factory)
    foreign = await client.post(
        path,
        headers={
            **await delegate_headers(client, other["access_token"], key="archive"),
            "X-Workspace-ID": "2",
        },
    )
    assert foreign.status_code == 403
    assert (
        await client.post("/api/v1/account/oauth/grants/grant-1/revoke")
    ).status_code == 200
    denied = await client.post(path, headers=headers)
    assert denied.status_code == 401 and denied.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("entity", ["pages", "components"])
async def test_expired_archive_key_does_not_recover_old_response(
    oauth_mutation_client, entity
):
    """归档记录过期后按新写入规则失败，幂等回滚不能触发 ORM 隐式异步加载或复活目标。"""
    client, factory, access, _ = oauth_mutation_client
    headers = await delegate_headers(
        client, access["access_token"], key="archive-expired"
    )
    path = f"/api/v1/{entity}/1/archive"
    assert (await client.post(path, headers=headers)).status_code == 200
    async with factory() as session:
        await session.execute(
            update(ApiIdempotencyRecord).values(
                expires_at=utc_now() - timedelta(seconds=1)
            )
        )
        await session.commit()
    response = await client.post(path, headers=headers)
    assert response.status_code == 404
