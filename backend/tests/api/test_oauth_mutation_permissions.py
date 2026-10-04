"""文件功能：验证真实委托 Mutation 提交、动态 Job 权限及跨用户/空间隔离。"""

import pytest
from app.models.api_mutation_job import ApiMutationJob
from sqlalchemy import func, select

from tests.fixtures.oauth_mutations import (
    SOURCE,
    delegate_headers,
    other_user_access,
    submit_edit,
)


@pytest.mark.parametrize("kind", ["page", "component"])
async def test_read_scope_cannot_submit_mutation(oauth_mutation_client, kind):
    """仅有读取 Scope 的主体不能提交重任务，失败后数据库没有受理 Job。"""
    client, factory, access, _ = oauth_mutation_client
    headers = await delegate_headers(
        client, access["access_token"], scopes=[kind + ":read"]
    )
    payload = (
        {"project_id": 1, "name": "页面", "source_code": SOURCE}
        if kind == "page"
        else {
            "workspace_id": 1,
            "import_name": "NewCard",
            "name": "组件",
            "source_code": SOURCE,
        }
    )
    response = await client.post(
        f"/api/v1/jobs/mutations/{kind}s", json=payload, headers=headers
    )
    assert (
        response.status_code == 403 and response.json()["code"] == "INSUFFICIENT_SCOPE"
    )
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 0
        )


@pytest.mark.parametrize("kind", ["page", "component"])
async def test_dynamic_job_permissions_use_persisted_kind(oauth_mutation_client, kind):
    """查询只需正确读取权限；取消/retry 需正确写权限，调用方 resource_type 无法改派。"""
    client, _, access, _ = oauth_mutation_client
    job = await submit_edit(client, access["access_token"], kind)
    path = "/api/v1/jobs/mutations/" + job["job_id"]
    other = "component" if kind == "page" else "page"
    read = await delegate_headers(
        client, access["access_token"], scopes=[kind + ":read"]
    )
    wrong = await delegate_headers(
        client, access["access_token"], scopes=[other + ":read", other + ":write"]
    )
    assert (await client.get(path, headers=read)).status_code == 200
    forged = await client.get(path, params={"resource_type": other}, headers=wrong)
    assert forged.status_code == 403 and forged.json()["code"] == "INSUFFICIENT_SCOPE"
    for action in ("cancel", "retry"):
        for headers in (read, wrong):
            response = await client.post(
                path + "/" + action, params={"resource_type": other}, headers=headers
            )
            assert (
                response.status_code == 403
                and response.json()["code"] == "INSUFFICIENT_SCOPE"
            )
    write = await delegate_headers(
        client, access["access_token"], scopes=[kind + ":write"], key="cancel"
    )
    canceled = await client.post(path + "/cancel", headers=write)
    assert canceled.status_code == 200 and canceled.json()["status"] == "canceled"
    assert (await client.get(path, headers=write)).status_code == 403


async def test_two_delegated_users_cannot_access_other_space_jobs(
    oauth_mutation_client,
):
    """两用户交错使用相同 key/operation；只获得自身 Job，伪造 Header 不能跨空间管理。"""
    client, factory, access, _ = oauth_mutation_client
    other = await other_user_access(client, factory)
    headers = await delegate_headers(client, access["access_token"])
    other_headers = {
        **await delegate_headers(client, other["access_token"]),
        "X-Workspace-ID": "2",
    }
    first = await client.post(
        "/api/v1/jobs/mutations/pages",
        json={"project_id": 1, "source_code": SOURCE, "name": "页面"},
        headers=headers,
    )
    second = await client.post(
        "/api/v1/jobs/mutations/pages",
        json={"project_id": 2, "source_code": SOURCE, "name": "页面"},
        headers=other_headers,
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] != second.json()["job_id"]
    for own, foreign, own_headers in (
        (first, second, headers),
        (second, first, other_headers),
    ):
        own_path = "/api/v1/jobs/mutations/" + own.json()["job_id"]
        foreign_path = "/api/v1/jobs/mutations/" + foreign.json()["job_id"]
        assert (await client.get(own_path, headers=own_headers)).status_code == 200
        spoofed = {
            **own_headers,
            "X-Workspace-ID": "1" if own_headers["X-Workspace-ID"] == "2" else "2",
        }
        for action in ("status", "cancel", "retry"):
            response = (
                await client.get(foreign_path, headers=spoofed)
                if action == "status"
                else await client.post(foreign_path + "/" + action, headers=spoofed)
            )
            assert (
                response.status_code == 403
                and response.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"
            )
    async with factory() as session:
        jobs = (
            await session.scalars(
                select(ApiMutationJob).order_by(ApiMutationJob.created_by)
            )
        ).all()
        assert [(job.created_by, job.workspace_id, job.status) for job in jobs] == [
            (1, 1, "pending"),
            (2, 2, "pending"),
        ]
