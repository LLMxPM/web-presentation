"""文件功能：测试异步 Mutation Job 生命周期、CAS 租约更新与超时恢复 Sweeper。"""

from __future__ import annotations

from datetime import timedelta
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.models.api_mutation_job import ApiMutationJob
from app.models.enums import RecordStatus, UserRole
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.external_api import ExternalPageCreateMutationRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.mutation_job_service import MutationJobService
from app.core.exceptions import AppException


@pytest.mark.asyncio
async def test_mutation_job_enqueue_and_claim(app_session: AsyncSession) -> None:
    """测试 Mutation Job 创建、短事务认领与租约持有。"""

    user = User(
        username="mutation_user",
        password_hash="hash",
        display_name="User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()

    ws = Workspace(code="ws-mut-01", name="WS", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    app_session.add(ws)
    await app_session.commit()

    service = MutationJobService(app_session, worker_id="test-worker-1")
    req = ExternalPageCreateMutationRequest(
        project_id=1,
        name="Page 01",
        source_code="<template><div>Hello</div></template>",
    )

    job = await service.enqueue_page_create_job(workspace_id=ws.id, user_id=user.id, payload=req)
    await app_session.commit()

    assert job.status == "pending"
    assert job.attempt_count == 0
    assert job.job_type == "page_create"

    # 阶段 1：认领任务
    claimed_job = await service.claim_next_pending_job()
    assert claimed_job is not None
    assert claimed_job.id == job.id
    assert claimed_job.status == "running"
    assert claimed_job.worker_id == "test-worker-1"
    assert claimed_job.lease_generation == 1
    assert claimed_job.lease_expires_at is not None

    # 再次认领时已无可用 pending 任务
    service_2 = MutationJobService(app_session, worker_id="test-worker-2")
    claimed_again = await service_2.claim_next_pending_job()
    assert claimed_again is None


@pytest.mark.asyncio
async def test_mutation_job_lease_sweeper(app_session: AsyncSession) -> None:
    """测试 Sweeper 自动回收超时孤儿任务并进行指数退避或标记终态失败。"""

    user = User(
        username="mutation_user_2",
        password_hash="hash",
        display_name="User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()

    ws = Workspace(code="ws-mut-02", name="WS", created_by=user.id, updated_by=user.id, status=RecordStatus.ACTIVE.value)
    app_session.add(ws)
    await app_session.flush()

    # 插入一个已经超时的 running 任务
    expired_time = utc_now() - timedelta(seconds=60)
    job = ApiMutationJob(
        job_id="expired-job-uuid",
        job_type="page_create",
        workspace_id=ws.id,
        payload_json={"page_code": "page-test"},
        status="running",
        worker_id="crashed-worker-99",
        lease_generation=1,
        lease_expires_at=expired_time,
        attempt_count=0,
        max_attempts=3,
        created_by=user.id,
        created_at=utc_now(),
    )
    app_session.add(job)
    await app_session.commit()

    # 执行回收
    recovered = await MutationJobService.recover_expired_running_jobs()
    assert recovered == 1

    await app_session.refresh(job)
    assert job.status == "pending"
    assert job.attempt_count == 1
    assert job.worker_id is None
    assert job.last_error_code == "LEASE_TIMEOUT_RECOVERED"


@pytest.mark.asyncio
async def test_mutation_cancel_and_manual_retry_contract(app_session: AsyncSession) -> None:
    """验证 pending/running 取消语义以及人工重试创建不可变的新任务。"""

    user = User(
        username="mutation_contract_user",
        password_hash="hash",
        display_name="User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    app_session.add(user)
    await app_session.flush()
    workspace = Workspace(
        code="ws-mut-contract",
        name="WS",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    app_session.add(workspace)
    await app_session.flush()
    service = MutationJobService(app_session, worker_id="contract-worker")

    pending = ApiMutationJob(
        job_id="pending-cancel-job",
        job_type="page_edit",
        workspace_id=workspace.id,
        target_id=7,
        base_version_no=3,
        payload_json={"page_id": 7, "base_version_no": 3, "edits": []},
        status="pending",
        max_attempts=3,
        created_by=user.id,
        created_at=utc_now(),
    )
    running = ApiMutationJob(
        job_id="running-cancel-job",
        job_type="component_edit",
        workspace_id=workspace.id,
        target_id=8,
        source_hash="old-hash",
        payload_json={"component_id": 8, "base_draft_hash": "old-hash", "edits": []},
        status="running",
        max_attempts=3,
        created_by=user.id,
        created_at=utc_now(),
    )
    failed = ApiMutationJob(
        job_id="retryable-failed-job",
        job_type="page_edit",
        workspace_id=workspace.id,
        target_id=9,
        base_version_no=4,
        payload_json={"page_id": 9, "base_version_no": 4, "edits": [{"type": "replace"}]},
        status="failed",
        error_json={"code": "RUNTIME_UNAVAILABLE", "message": "down", "retryable": True},
        max_attempts=3,
        created_by=user.id,
        created_at=utc_now(),
    )
    app_session.add_all([pending, running, failed])
    await app_session.commit()

    status, pending_response = await service.request_cancel_job(pending)
    assert status == 200
    assert pending_response.status == "canceled"
    status, running_response = await service.request_cancel_job(running)
    assert status == 202
    assert running_response.status == "running"
    assert running_response.cancel_requested_at is not None

    retried = await service.enqueue_retry_job(failed, user_id=user.id, idempotency_record_id=None)
    await app_session.commit()
    response = await service.get_job_response(retried)
    assert response.status == "pending"
    assert response.retry_of_job_id == failed.job_id
    assert retried.payload_json == failed.payload_json
    assert retried.base_version_no == 4
    assert failed.status == "failed"

    with pytest.raises(AppException) as caught:
        await service.request_cancel_job(failed)
    assert caught.value.code == "MUTATION_JOB_NOT_CANCELABLE"
