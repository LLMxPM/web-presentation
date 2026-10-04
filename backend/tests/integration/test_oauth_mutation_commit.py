"""文件功能：从真实委托 HTTP 入队验证 Mutation 提交前基线、取消及凭证失效边界。"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.api_mutation_job import ApiMutationJob
from app.models.oauth_credential import OAuthToken
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.workspace_component import WorkspaceComponent
from app.services import mutation_job_service
from app.services.mutation_job_service import MutationJobService
from app.services.oauth.protocol import credential_digest
from sqlalchemy import func, select, update

from tests.fixtures.oauth_mutations import SOURCE, delegate_headers, submit_edit

PREPARED = "<template><div>已通过规划阶段的候选源码</div></template>"


async def claim(factory, monkeypatch):
    """认领真实隔离任务，并把提交阶段的独立 Session 固定到同一测试库。"""
    monkeypatch.setattr(mutation_job_service, "get_session_factory", lambda: factory)
    async with factory() as session:
        worker = MutationJobService(session, worker_id="oauth-test-worker")
        job = await worker.claim_next_pending_job()
        assert job is not None and job.status == "running"
    return worker, job


def prepared():
    """提供受控规划结果，只验证领域提交阶段；不作为 Renderer 或源码诊断验收。"""
    return SimpleNamespace(
        success=True, target_page_id=1, target_component_id=1, prepared_content=PREPARED
    )


@pytest.mark.parametrize(
    "kind,change",
    [
        ("page", "version"),
        ("component", "version"),
        ("component", "draft"),
        ("metadata", "version"),
        ("metadata", "draft"),
    ],
)
async def test_commit_conflict_cannot_overwrite_or_upgrade_baseline(
    oauth_mutation_client, monkeypatch, kind, change
):
    """诊断后实体变更使原任务确定性失败，不能覆盖用户更新，也不能人工 retry 升级基线。"""
    client, factory, access, _ = oauth_mutation_client
    if kind == "metadata":
        result = await client.post(
            "/api/v1/jobs/mutations/components/metadata",
            json={"component_id": 1, "component_type": "atomic"},
            headers=await delegate_headers(client, access["access_token"]),
        )
        assert result.status_code == 202, result.text
        accepted = result.json()
    else:
        accepted = await submit_edit(client, access["access_token"], kind)
    worker, job = await claim(factory, monkeypatch)
    model = Page if kind == "page" else WorkspaceComponent
    changed = (
        {"current_version_no": 2}
        if change == "version"
        else {"content": "<template><div>用户新草稿</div></template>"}
    )
    async with factory() as session:
        await session.execute(update(model).where(model.id == 1).values(**changed))
        await session.commit()
    with pytest.raises(AppException) as caught:
        await worker._finalize_success(job.id, job.lease_generation, prepared())
    code = (
        "PAGE_CONCURRENT_MODIFIED"
        if kind == "page"
        else "COMPONENT_CONCURRENT_MODIFIED"
    )
    assert caught.value.code == code
    await worker._handle_job_failure(job.id, job.lease_generation, caught.value)
    headers = await delegate_headers(
        client, access["access_token"], key="retry-conflict"
    )
    path = "/api/v1/jobs/mutations/" + accepted["job_id"]
    response = await client.get(path, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "failed"
    assert (
        response.json()["error"]["code"] == code
        and response.json()["error"]["retryable"] is False
    )
    retry = await client.post(path + "/retry", headers=headers)
    assert (
        retry.status_code == 409
        and retry.json()["code"] == "MUTATION_JOB_NOT_RETRYABLE"
    )
    async with factory() as session:
        entity = await session.get(model, 1)
        assert getattr(entity, "page_content" if kind == "page" else "content") == (
            changed.get("content") or SOURCE
        )
        stored = await session.get(ApiMutationJob, job.id)
        assert stored.base_version_no == (1 if kind == "page" else 0)
        assert stored.attempt_count == 0


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_cancel_and_complete_commit_order(
    oauth_mutation_client, monkeypatch, cancel_first
):
    """取消先提交则无实体写入；完成先提交则取消冲突，保留已完成的唯一版本。"""
    client, factory, access, _ = oauth_mutation_client
    accepted = await submit_edit(client, access["access_token"], "page")
    worker, job = await claim(factory, monkeypatch)
    headers = await delegate_headers(client, access["access_token"], key="cancel")
    path = "/api/v1/jobs/mutations/" + accepted["job_id"] + "/cancel"
    if cancel_first:
        response = await client.post(path, headers=headers)
        assert response.status_code == 202 and response.json()["status"] == "running"
        assert response.json()["cancel_requested_at"] is not None
    await worker._finalize_success(job.id, job.lease_generation, prepared())
    if not cancel_first:
        response = await client.post(path, headers=headers)
        assert (
            response.status_code == 409
            and response.json()["code"] == "MUTATION_JOB_NOT_CANCELABLE"
        )
    async with factory() as session:
        stored = await session.get(ApiMutationJob, job.id)
        page = await session.get(Page, 1)
        assert stored.status == ("canceled" if cancel_first else "succeeded")
        assert page.page_content == (SOURCE if cancel_first else PREPARED)
        assert page.current_version_no == (1 if cancel_first else 2)
        assert await session.scalar(
            select(func.count())
            .select_from(PageVersion)
            .where(PageVersion.version_no == 2)
        ) == (0 if cancel_first else 1)


@pytest.mark.parametrize("invalidated", ["revoke", "expires"])
async def test_invalidated_credential_does_not_cancel_accepted_job(
    oauth_mutation_client, monkeypatch, invalidated
):
    """凭证失效拒绝后续 Job 请求，已受理领域任务仍可按现有用户权限完成。"""
    client, factory, access, _ = oauth_mutation_client
    accepted = await submit_edit(client, access["access_token"], "page")
    headers = await delegate_headers(client, access["access_token"])
    if invalidated == "revoke":
        assert (
            await client.post("/api/v1/account/oauth/grants/grant-1/revoke")
        ).status_code == 200
    else:
        async with factory() as session:
            await session.execute(
                update(OAuthToken)
                .where(
                    OAuthToken.token_hash
                    == credential_digest(headers["Authorization"].split()[1])
                )
                .values(expires_at=utc_now() - timedelta(seconds=1))
            )
            await session.commit()
    path = "/api/v1/jobs/mutations/" + accepted["job_id"]
    for action in ("status", "cancel", "retry"):
        response = (
            await client.get(path, headers=headers)
            if action == "status"
            else await client.post(path + "/" + action, headers=headers)
        )
        assert (
            response.status_code == 401 and response.json()["code"] == "UNAUTHENTICATED"
        )
    worker, job = await claim(factory, monkeypatch)
    await worker._finalize_success(job.id, job.lease_generation, prepared())
    async with factory() as session:
        assert (await session.get(ApiMutationJob, job.id)).status == "succeeded"
        assert (await session.get(Page, 1)).current_version_no == 2
