"""文件功能：验证选定空间限制真实 PAT/委托读写及 Mutation Job，跨空间失败不能留下副作用。"""

import pytest
from sqlalchemy import func, select

from app.models.api_mutation_job import ApiMutationJob
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from tests.fixtures.oauth_mutations import SOURCE, delegate_headers


async def headers_for(source, fixture):
    """返回真实发行的两空间凭证，默认选定空间一。"""
    client, _, access, pat = fixture
    return await delegate_headers(client, access["access_token"]) if source == "delegated" else {
        "Authorization": "Bearer " + pat, "X-Workspace-ID": "1", "Idempotency-Key": "original"}


@pytest.mark.parametrize("source", ["pat", "delegated"])
async def test_selected_workspace_blocks_object_access_before_writes(multi_workspace_client, source):
    """同一用户拥有两空间权限，Header 空间一仍不能读取、修改、归档空间二对象。"""
    client, factory, _, _ = multi_workspace_client
    headers = await headers_for(source, multi_workspace_client)
    for kind, view, body in (("page", "source", {"title": "错误修改"}), ("component", "draft", {"name": "错误修改"})):
        path = f"/api/v1/{kind}s/2"
        responses = [await client.get(path + "/" + view, headers=headers),
                     await client.patch(path, json=body, headers=headers),
                     await client.post(path + "/archive", headers=headers)]
        for response in responses:
            assert response.status_code == 404, response.text
            assert response.json()["code"] == "WORKSPACE_CONTEXT_MISMATCH"
        payload = {"project_id": 2, "name": "新页面", "source_code": SOURCE} if kind == "page" else {
            "workspace_id": 2, "import_name": "NewCard", "name": "新组件", "source_code": SOURCE}
        create = await client.post(f"/api/v1/jobs/mutations/{kind}s", json=payload, headers=headers)
        assert create.status_code == 404 and create.json()["code"] == "WORKSPACE_CONTEXT_MISMATCH"
    async with factory() as session:
        page, component = await session.get(Page, 2), await session.get(WorkspaceComponent, 2)
        assert page.title == "空间二页面" and page.status == "active"
        assert component.name == "空间二组件" and component.status == "active"
        assert await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 0
    # 不提供 Header 的已有 API 客户端仍按凭证范围访问；明确选择正确空间则正常写入。
    unselected = {key: value for key, value in headers.items() if key != "X-Workspace-ID"}
    assert (await client.get("/api/v1/pages/2/source", headers=unselected)).status_code == 200
    matching = {**headers, "X-Workspace-ID": "2"}
    updated = await client.patch("/api/v1/pages/2", json={"title": "正确修改"}, headers=matching)
    assert updated.status_code == 200 and updated.json()["title"] == "正确修改"


@pytest.mark.parametrize("source", ["pat", "delegated"])
async def test_dynamic_jobs_follow_selected_workspace(multi_workspace_client, source):
    """动态 status/cancel/retry 都受 Header 约束；错误空间不取消任务或创建重试。"""
    client, factory, _, _ = multi_workspace_client
    headers = await headers_for(source, multi_workspace_client)
    matching = {**headers, "X-Workspace-ID": "2"}
    created = await client.post("/api/v1/jobs/mutations/pages", json={"project_id": 2, "name": "新页面", "source_code": SOURCE}, headers=matching)
    assert created.status_code == 202, created.text
    path = "/api/v1/jobs/mutations/" + created.json()["job_id"]
    for method, suffix in (("GET", ""), ("POST", "/cancel"), ("POST", "/retry")):
        blocked = await client.request(method, path + suffix, headers=headers)
        assert blocked.status_code == 404 and blocked.json()["code"] == "WORKSPACE_CONTEXT_MISMATCH"
    async with factory() as session:
        jobs = (await session.scalars(select(ApiMutationJob))).all()
        assert len(jobs) == 1 and jobs[0].status == "pending" and jobs[0].cancel_requested_at is None
    assert (await client.get(path, headers=matching)).status_code == 200
    unselected = {key: value for key, value in headers.items() if key != "X-Workspace-ID"}
    assert (await client.get(path, headers=unselected)).status_code == 200
    invalid_key = await client.post(path + "/cancel", headers={**matching, "Idempotency-Key": "k" * 129})
    assert invalid_key.status_code == 400 and invalid_key.json()["code"] == "INVALID_IDEMPOTENCY_KEY"
    canceled = await client.post(path + "/cancel", headers={**matching, "Idempotency-Key": "cancel"})
    assert canceled.status_code == 200 and canceled.json()["status"] == "canceled"


async def test_backend_key_length_preserves_business_error(multi_workspace_client):
    """128 字符原键可写入，129 字符和非标识值统一返回业务 400，而非自动裁剪或 422。"""
    client, factory, _, _ = multi_workspace_client
    headers = await headers_for("pat", multi_workspace_client)
    for key in ("k" * 129, "has space", " k "):
        invalid = await client.patch("/api/v1/pages/1", json={"title": "不得写入"}, headers={**headers, "Idempotency-Key": key})
        assert invalid.status_code == 400 and invalid.json()["code"] == "INVALID_IDEMPOTENCY_KEY"
    async with factory() as session:
        assert (await session.get(Page, 1)).title == "测试页面"
    valid = await client.patch("/api/v1/pages/1", json={"title": "边界成功"}, headers={**headers, "Idempotency-Key": "k" * 128})
    assert valid.status_code == 200 and valid.json()["title"] == "边界成功"
