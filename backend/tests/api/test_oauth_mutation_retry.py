"""文件功能：验证委托人工 retry 的新任务关联、原基线保留及幂等恢复。"""

import pytest
from app.models.api_mutation_job import ApiMutationJob
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from sqlalchemy import select, update

from tests.fixtures.oauth_mutations import delegate_headers, submit_edit


@pytest.mark.parametrize("kind", ["page", "component"])
async def test_retry_creates_one_new_job_and_preserves_original_baseline(
    oauth_mutation_client, kind
):
    """failed 查询仍为 HTTP 200；人工 retry 创建关联新 ID，草稿变化不能升级原基线。"""
    client, factory, access, _ = oauth_mutation_client
    accepted = await submit_edit(client, access["access_token"], kind)
    path = "/api/v1/jobs/mutations/" + accepted["job_id"]
    headers = await delegate_headers(client, access["access_token"], key="retry")
    async with factory() as session:
        original = await session.scalar(select(ApiMutationJob))
        original.status = "failed"
        original.error_json = {
            "code": "RUNTIME_UNAVAILABLE",
            "message": "测试故障",
            "retryable": True,
        }
        original_id = original.id
        baseline = (
            original.payload_json,
            original.base_version_no,
            original.source_hash,
        )
        model = Page if kind == "page" else WorkspaceComponent
        await session.execute(
            update(model).where(model.id == 1).values(current_version_no=4)
        )
        await session.commit()
    queried = await client.get(path, headers=headers)
    assert queried.status_code == 200 and queried.json()["status"] == "failed"
    assert queried.json()["error"]["retryable"] is True
    retry = await client.post(path + "/retry", headers=headers)
    assert retry.status_code == 202, retry.text
    assert retry.json()["job_id"] != accepted["job_id"]
    assert retry.json()["retry_of_job_id"] == accepted["job_id"]
    replay = await client.post(
        path + "/retry",
        headers=await delegate_headers(client, access["access_token"], key="retry"),
    )
    assert replay.status_code == 202 and replay.json() == retry.json()
    async with factory() as session:
        jobs = (
            await session.scalars(select(ApiMutationJob).order_by(ApiMutationJob.id))
        ).all()
        assert len(jobs) == 2
        retried = jobs[1]
        assert retried.retry_of_job_id == original_id and retried.status == "pending"
        assert (
            retried.payload_json,
            retried.base_version_no,
            retried.source_hash,
        ) == baseline


@pytest.mark.parametrize(
    "status,retryable",
    [("pending", True), ("succeeded", True), ("canceled", True), ("failed", False)],
)
async def test_retry_rejects_non_retryable_jobs(
    oauth_mutation_client, status, retryable
):
    """终态和错误可重试标记共同约束人工 retry，不能重放已成功或基线冲突写入。"""
    client, factory, access, _ = oauth_mutation_client
    accepted = await submit_edit(client, access["access_token"], "component")
    async with factory() as session:
        job = await session.scalar(select(ApiMutationJob))
        job.status = status
        job.error_json = {
            "code": "COMPONENT_CONCURRENT_MODIFIED",
            "message": "冲突",
            "retryable": retryable,
        }
        await session.commit()
    response = await client.post(
        "/api/v1/jobs/mutations/" + accepted["job_id"] + "/retry",
        headers=await delegate_headers(client, access["access_token"], key="retry"),
    )
    assert (
        response.status_code == 409
        and response.json()["code"] == "MUTATION_JOB_NOT_RETRYABLE"
    )
    async with factory() as session:
        assert len((await session.scalars(select(ApiMutationJob))).all()) == 1
