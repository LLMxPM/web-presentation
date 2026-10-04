"""文件功能：验证真实委托提交的队列语义、令牌轮换重放和组件隐式基线的稳定性。"""

import asyncio

import pytest
from app.models.api_idempotency_record import ApiIdempotencyRecord
from app.models.api_mutation_job import ApiMutationJob
from app.models.workspace_component import WorkspaceComponent
from app.schemas.external_api import (
    ExternalComponentApplyEditsMutationRequest,
    ExternalComponentMetadataMutationRequest,
)
from app.services.idempotency_service import IdempotencyService
from sqlalchemy import func, select, update

from tests.fixtures.oauth_mutations import SOURCE, delegate_headers, refresh_access

CASES = [
    (
        "/api/v1/pages",
        {"project_id": 1, "name": "页面", "source_code": SOURCE},
        "page_create",
        "page.create",
    ),
    (
        "/api/v1/jobs/mutations/pages",
        {"project_id": 1, "name": "页面", "source_code": SOURCE},
        "page_create",
        "jobs.mutation.page.create",
    ),
    (
        "/api/v1/pages/1/edits",
        {
            "page_id": 1,
            "base_version_no": 1,
            "edits": [{"type": "replace_exact", "old_text": "原始", "new_text": "新"}],
        },
        "page_edit",
        "page.edit",
    ),
    (
        "/api/v1/jobs/mutations/pages/edits",
        {
            "page_id": 1,
            "base_version_no": 1,
            "edits": [{"type": "replace_exact", "old_text": "原始", "new_text": "新"}],
        },
        "page_edit",
        "jobs.mutation.page.edit",
    ),
    (
        "/api/v1/components",
        {
            "workspace_id": 1,
            "import_name": "NewCard",
            "name": "组件",
            "source_code": SOURCE,
        },
        "component_create",
        "component.create",
    ),
    (
        "/api/v1/jobs/mutations/components",
        {
            "workspace_id": 1,
            "import_name": "NewCard",
            "name": "组件",
            "source_code": SOURCE,
        },
        "component_create",
        "jobs.mutation.component.create",
    ),
    (
        "/api/v1/components/1/edits",
        {
            "component_id": 1,
            "base_version_no": 0,
            "edits": [{"type": "replace_exact", "old_text": "原始", "new_text": "新"}],
        },
        "component_edit",
        "component.edit",
    ),
    (
        "/api/v1/jobs/mutations/components/edits",
        {
            "component_id": 1,
            "base_version_no": 0,
            "edits": [{"type": "replace_exact", "old_text": "原始", "new_text": "新"}],
        },
        "component_edit",
        "jobs.mutation.component.edit",
    ),
    (
        "/api/v1/jobs/mutations/components/metadata",
        {"component_id": 1, "component_type": "atomic"},
        "component_metadata",
        "jobs.mutation.component.metadata",
    ),
]


@pytest.mark.parametrize("path,payload,kind,operation", CASES)
async def test_queue_replay_survives_new_delegation_refresh_and_pat(
    oauth_mutation_client, path, payload, kind, operation
):
    """重任务只入一个 Job；新委托、刷新及同用户 PAT 用相同 key 恢复原受理结果。"""
    client, factory, access, pat = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"])
    first = await client.post(path, json=payload, headers=headers)
    assert first.status_code == 202, first.text
    # 丢失响应的恢复不依赖客户端保存 Job ID：重新交换后按原 key 请求即可。
    second = await client.post(
        path,
        json=payload,
        headers=await delegate_headers(client, access["access_token"]),
    )
    assert second.status_code == 202 and second.json() == first.json()
    renewed = await refresh_access(client, access["refresh_token"])
    replay = await client.post(
        path,
        json=payload,
        headers=await delegate_headers(client, renewed["access_token"]),
    )
    assert replay.status_code == 202 and replay.json() == first.json()
    pat_replay = await client.post(
        path, json=payload, headers={**headers, "Authorization": "Bearer " + pat}
    )
    assert pat_replay.status_code == 202 and pat_replay.json() == first.json()
    async with factory() as session:
        jobs = (await session.scalars(select(ApiMutationJob))).all()
        assert len(jobs) == 1 and jobs[0].job_type == kind and jobs[0].created_by == 1
        assert jobs[0].status == "pending"
        record = await session.get(ApiIdempotencyRecord, jobs[0].idempotency_record_id)
        assert (
            record.operation == operation
            and record.user_id == 1
            and record.workspace_id == 1
        )


@pytest.mark.parametrize("path,payload,kind,operation", CASES[6:])
async def test_implicit_component_baseline_does_not_drift_during_replay(
    oauth_mutation_client, path, payload, kind, operation
):
    """服务端填入的草稿/版本基线必须沿用首个任务；组件变化不能把同请求变成冲突或新任务。"""
    client, factory, access, _ = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"])
    first = await client.post(path, json=payload, headers=headers)
    assert first.status_code == 202, first.text
    async with factory() as session:
        old = await session.scalar(select(ApiMutationJob))
        frozen_payload = dict(old.payload_json)
        schema = (
            ExternalComponentMetadataMutationRequest
            if kind == "component_metadata"
            else ExternalComponentApplyEditsMutationRequest
        )
        # 历史实体 edits/metadata 指纹包含补齐值；Job edits 别名指纹保留客户端原始省略值。
        legacy_payload = (
            frozen_payload
            if operation != "jobs.mutation.component.edit"
            else schema.model_validate(payload).model_dump(mode="json")
        )
        record = await session.get(ApiIdempotencyRecord, old.idempotency_record_id)
        assert (
            record.request_fingerprint
            == IdempotencyService.calculate_request_fingerprint(
                http_method="POST",
                path=path,
                json_data=legacy_payload,
            )
        )
        await session.execute(
            update(WorkspaceComponent)
            .where(WorkspaceComponent.id == 1)
            .values(
                content="<template><div>已修改草稿</div></template>",
                current_version_no=2,
            )
        )
        await session.commit()
    replay = await client.post(path, json=payload, headers=headers)
    assert replay.status_code == 202, replay.text
    assert replay.json() == first.json()
    async with factory() as session:
        job = await session.scalar(select(ApiMutationJob))
        assert job.payload_json == frozen_payload
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 1
        )


async def test_same_key_different_payload_is_rejected(oauth_mutation_client):
    """即使用户与令牌相同，相同 key 改变源码也不能再次入队。"""
    client, factory, access, _ = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"])
    path, payload, _, _ = CASES[0]
    assert (await client.post(path, json=payload, headers=headers)).status_code == 202
    conflict = await client.post(
        path, json={**payload, "source_code": "changed"}, headers=headers
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"
    )
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 1
        )


@pytest.mark.parametrize("path,payload,kind,operation", CASES[6:])
async def test_explicit_component_baseline_change_is_still_rejected(
    oauth_mutation_client, path, payload, kind, operation
):
    """沿用隐式基线不能掩盖调用方显式更改版本/hash 的异载荷冲突。"""
    client, factory, access, _ = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"])
    assert (await client.post(path, json=payload, headers=headers)).status_code == 202
    conflict = await client.post(
        path,
        json={**payload, "base_version_no": 9, "base_draft_hash": "f" * 64},
        headers=headers,
    )
    assert (
        conflict.status_code == 409
        and conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"
    )
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 1
        )


async def test_concurrent_duplicate_acceptance_and_alias_namespaces(
    oauth_mutation_client,
):
    """独立请求竞争后同键恢复一个 Job；切换别名属于既有不同 operation，不能假定跨路径重放。"""
    client, factory, access, _ = oauth_mutation_client
    headers = await delegate_headers(client, access["access_token"])
    path, payload, _, _ = CASES[0]
    results = await asyncio.gather(
        *(client.post(path, json=payload, headers=headers) for _ in range(2))
    )
    assert all(result.status_code in (202, 409) for result in results)
    accepted = next(result for result in results if result.status_code == 202)
    replay = await client.post(path, json=payload, headers=headers)
    assert replay.status_code == 202 and replay.json() == accepted.json()
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 1
        )
    alias = await client.post(CASES[1][0], json=payload, headers=headers)
    assert (
        alias.status_code == 202 and alias.json()["job_id"] != accepted.json()["job_id"]
    )
    async with factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ApiMutationJob)) == 2
        )
