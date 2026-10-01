"""文件功能：验证渲染与构建任务的全局与工作空间并发配额限制、排队等待与终态释放。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.models.render_attempt import RenderAttempt
from app.models.render_execution import RenderWorker
from app.models.render_request import RenderRequest
from app.services.project_build_service import ProjectBuildService
from app.services.rendering.coordinator import RenderCoordinator
from app.services.rendering.repository import RenderRepository
from tests.integration.test_project_build import create_active_project
from tests.integration.test_project_build_job_lease import _create_build_job


async def _get_latest_attempt(session: AsyncSession, request_id: int) -> RenderAttempt | None:
    """查询指定 request 的最新 attempt 记录。"""
    res = await session.execute(
        select(RenderAttempt)
        .where(RenderAttempt.request_id == request_id)
        .order_by(RenderAttempt.id.desc())
    )
    return res.scalars().first()


async def _get_worker(session: AsyncSession, worker_id: str) -> RenderWorker | None:
    """查询指定 worker_id 的 Worker 记录。"""
    res = await session.execute(
        select(RenderWorker).where(RenderWorker.worker_id == worker_id)
    )
    return res.scalars().first()


def _make_render_request(
    *,
    request_key: str,
    workspace_id: int,
    project_id: int | None = None,
    schedule_category: str = "background",
) -> RenderRequest:
    """构造用于测试配额的渲染请求记录。"""
    now = utc_now()
    return RenderRequest(
        request_key=request_key,
        logical_owner_key=f"quota-test:{request_key}",
        business_stage="screenshot",
        operation="page.capture",
        schedule_category=schedule_category,
        workspace_id=workspace_id,
        project_id=project_id,
        status="queued",
        input_digest=f"input-{request_key}",
        render_digest=f"render-{request_key}",
        request_digest=f"request-{request_key}",
        render_profile_digest="profile.v1",
        deadline_at=now + timedelta(seconds=120),
        trace_id=f"trace-{request_key}",
        snapshot_ref={},
        operation_options={},
        viewport={"width": 1920, "height": 1080},
    )


def _make_render_worker(*, worker_id: str, epoch: str = "epoch-1") -> RenderWorker:
    """构造用于测试的就绪空闲 Renderer Worker 记录。"""
    now = utc_now()
    return RenderWorker(
        worker_id=worker_id,
        worker_epoch=epoch,
        service_base_url=f"http://{worker_id}:7400",
        status="ready",
        isolated=False,
        slot_generation=0,
        slot_state="idle",
        registered_at=now,
        last_heartbeat_at=now,
    )


@pytest.mark.asyncio
async def test_render_workspace_concurrency_limit_enforced(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工作空间活跃 attempt 达到上限时，同空间后续任务排队，其它空间或释放后可继续派发。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    settings = get_settings()
    monkeypatch.setattr(settings, "render_workspace_concurrency", 1)
    monkeypatch.setattr(settings, "render_global_concurrency", 5)

    session_factory = get_session_factory()
    coordinator = RenderCoordinator(session_factory=session_factory)

    async def fake_dispatch_attempt(attempt_id: int) -> int:
        return 1

    monkeypatch.setattr(coordinator, "_dispatch_attempt", fake_dispatch_attempt)

    async with session_factory() as session:
        session.add(_make_render_worker(worker_id="quota-worker-1"))
        session.add(_make_render_worker(worker_id="quota-worker-2"))
        req1 = _make_render_request(request_key=f"req-ws-1-{utc_now().timestamp()}", workspace_id=workspace_id, project_id=project_id)
        req2 = _make_render_request(request_key=f"req-ws-2-{utc_now().timestamp()}", workspace_id=workspace_id, project_id=project_id)
        session.add(req1)
        session.add(req2)
        await session.commit()
        req1_id, req2_id = req1.id, req2.id

    # 1. 第一次派发：req1 成功派发，工作空间活跃占用达到 1（上限）
    async with session_factory() as session:
        repo = RenderRepository(session)
        dispatched_1 = await coordinator._dispatch_once(session, repo)
    assert dispatched_1 == 1

    async with session_factory() as session:
        repo = RenderRepository(session)
        assert await repo.count_active_attempts(workspace_id=workspace_id) == 1
        req2_obj = await repo.get_request(req2_id)
        assert req2_obj is not None
        assert req2_obj.status == "queued"

    # 2. 第二次派发：由于工作空间配额已满，req2 被跳过，派发返回 0
    async with session_factory() as session:
        repo = RenderRepository(session)
        dispatched_2 = await coordinator._dispatch_once(session, repo)
    assert dispatched_2 == 0

    async with session_factory() as session:
        repo = RenderRepository(session)
        assert await repo.count_active_attempts(workspace_id=workspace_id) == 1
        req2_obj = await repo.get_request(req2_id)
        assert req2_obj is not None
        assert req2_obj.status == "queued"

    # 3. req1 的 attempt 终态完成，释放槽位
    async with session_factory() as session:
        repo = RenderRepository(session)
        req1_attempt = await _get_latest_attempt(session, req1_id)
        assert req1_attempt is not None
        req1_attempt.status = "succeeded"
        req1_attempt.active_occupancy = 0
        req1_attempt.cleanup_status = "released"
        worker = await _get_worker(session, req1_attempt.worker_id or "")
        if worker:
            worker.slot_state = "idle"
        await session.commit()

    # 4. 释放后再派发：req2 成功被派发
    async with session_factory() as session:
        repo = RenderRepository(session)
        dispatched_3 = await coordinator._dispatch_once(session, repo)
    assert dispatched_3 == 1

    async with session_factory() as session:
        repo = RenderRepository(session)
        assert await repo.count_active_attempts(workspace_id=workspace_id) == 1
        req2_attempt = await _get_latest_attempt(session, req2_id)
        assert req2_attempt is not None
        assert req2_attempt.status == "reserved"


@pytest.mark.asyncio
async def test_render_global_concurrency_limit_enforced(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全局活跃 attempt 达到上限时，即使不同工作空间也不再派发。"""

    ws1_id, p1_id = await create_active_project(authenticated_client)
    ws2_id, p2_id = await create_active_project(authenticated_client)

    settings = get_settings()
    monkeypatch.setattr(settings, "render_global_concurrency", 1)
    monkeypatch.setattr(settings, "render_workspace_concurrency", 5)

    session_factory = get_session_factory()
    coordinator = RenderCoordinator(session_factory=session_factory)

    async def fake_dispatch_attempt(attempt_id: int) -> int:
        return 1

    monkeypatch.setattr(coordinator, "_dispatch_attempt", fake_dispatch_attempt)

    async with session_factory() as session:
        session.add(_make_render_worker(worker_id="global-worker-1"))
        session.add(_make_render_worker(worker_id="global-worker-2"))
        req1 = _make_render_request(request_key=f"req-gl-1-{utc_now().timestamp()}", workspace_id=ws1_id, project_id=p1_id)
        req2 = _make_render_request(request_key=f"req-gl-2-{utc_now().timestamp()}", workspace_id=ws2_id, project_id=p2_id)
        session.add(req1)
        session.add(req2)
        await session.commit()
        req1_id, req2_id = req1.id, req2.id

    # 1. 第一次派发：req1 派发，全局活跃占用达到 1
    async with session_factory() as session:
        repo = RenderRepository(session)
        dispatched_1 = await coordinator._dispatch_once(session, repo)
    assert dispatched_1 == 1

    # 2. 第二次派发：全局配额已满，req2 虽然在不同空间也被拦截
    async with session_factory() as session:
        repo = RenderRepository(session)
        dispatched_2 = await coordinator._dispatch_once(session, repo)
    assert dispatched_2 == 0

    async with session_factory() as session:
        repo = RenderRepository(session)
        assert await repo.count_active_attempts() >= 1
        req2_obj = await repo.get_request(req2_id)
        assert req2_obj is not None
        assert req2_obj.status == "queued"

    # 3. req1 终态释放
    async with session_factory() as session:
        repo = RenderRepository(session)
        req1_attempt = await _get_latest_attempt(session, req1_id)
        assert req1_attempt is not None
        req1_attempt.status = "succeeded"
        req1_attempt.active_occupancy = 0
        req1_attempt.cleanup_status = "released"
        worker = await _get_worker(session, req1_attempt.worker_id or "")
        if worker:
            worker.slot_state = "idle"
        await session.commit()

    # 4. 释放后全局可用，req2 成功派发
    async with session_factory() as session:
        repo = RenderRepository(session)
        dispatched_3 = await coordinator._dispatch_once(session, repo)
    assert dispatched_3 == 1


@pytest.mark.asyncio
async def test_project_build_job_mutex_and_release(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目已有未完成构建任务时拒绝创建新任务（409），终态后允许再次创建。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    # 1. 发起第一个构建任务
    job1_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job1_id = job1_payload["id"]
    assert job1_payload["status"] == "pending"

    # 2. 尝试为同一项目创建第二个构建任务，必须被 409 PROJECT_BUILD_ALREADY_RUNNING 拦截
    conflict_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "PROJECT_BUILD_ALREADY_RUNNING"

    # 3. 模拟第一个任务进入 running 状态
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = ProjectBuildService(session, lease_owner="worker-build-1")
        claimed = await service.claim_job(job_id=job1_id)
        assert claimed is not None
        assert claimed.status == "running"

    # running 状态下再次尝试创建，依然 409
    conflict_response2 = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert conflict_response2.status_code == 409
    assert conflict_response2.json()["code"] == "PROJECT_BUILD_ALREADY_RUNNING"

    # 4. 将第一个任务标记为终态（如 failed 或 succeeded）
    async with session_factory() as session:
        job1 = await session.get(ProjectBuildJob, job1_id)
        assert job1 is not None
        job1.status = "failed"
        job1.lease_owner = None
        job1.lease_expires_at = None
        await session.commit()

    # 5. 终态后再次创建，成功允许发起新构建
    job2_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert job2_response.status_code == 200
    job2_payload = job2_response.json()
    assert job2_payload["id"] != job1_id
    assert job2_payload["status"] == "pending"
