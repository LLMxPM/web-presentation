"""文件功能：验证多 Backend 副本下任务协调器不重复提交、双协调者竞争只成功一次。"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.db.session import get_session_factory
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.project_build_job import ProjectBuildJob
from app.services.durable_job_lease_service import build_durable_worker_id, claim_pending_jobs
from app.services.page_screenshot_job_service import PageScreenshotJobService
from app.services.project_artifact_builder import ProjectArtifactSnapshot
from app.services.project_build_service import ProjectBuildService, run_project_build_job
from tests.integration.test_project_build import build_fake_snapshot, create_active_project
from tests.integration.test_project_build_job_lease import _create_build_job


async def _read_build_job(job_id: int) -> ProjectBuildJob:
    """读取构建任务当前持久化状态。"""

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        return job


async def _create_screenshot_job(authenticated_client: AsyncClient, *, name: str) -> int:
    """创建页面截图任务并返回任务 ID。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": f"{name}空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": f"{name}项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_content": f"<template><div>{name}</div></template>",
            "file_type": "vue",
            "title": f"{name}页",
            "status": "active",
        },
    )
    assert page_response.status_code == 200
    page_id = page_response.json()["id"]
    job_response = await authenticated_client.post(f"/api/pages/{page_id}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    return int(job_response.json()["id"])


@pytest.mark.asyncio
async def test_concurrent_build_claims_should_elect_single_winner(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """两个协调者并发领取同一构建任务时，只有一个成功并写入唯一 attempt。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])
    factory = get_session_factory()

    async def _claim(owner: str) -> ProjectBuildJob | None:
        async with factory() as session:
            return await ProjectBuildService(session, lease_owner=owner).claim_job(job_id=job_id)

    first, second = await asyncio.gather(_claim("coordinator-a"), _claim("coordinator-b"))
    winners = [job for job in (first, second) if job is not None]

    assert len(winners) == 1
    winner = winners[0]
    assert winner.status == "running"
    assert winner.attempt_count == 1
    assert winner.attempt_id
    assert winner.lease_owner in {"coordinator-a", "coordinator-b"}

    job = await _read_build_job(job_id)
    assert job.attempt_id == winner.attempt_id
    assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_double_dispatch_should_execute_build_only_once(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """BackgroundTasks 与队列循环重复调用执行入口时，领取 CAS 保证只派发一次。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])

    dispatch_count = 0

    async def fake_dispatch(self, **kwargs):  # noqa: ANN001, ARG002
        """记录 Runtime 派发次数。"""

        nonlocal dispatch_count
        dispatch_count += 1

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.RuntimeBuildClient.dispatch_project_build",
        fake_dispatch,
    )
    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    # 模拟 BackgroundTasks 与队列循环在同一时刻提交同一 job。
    await asyncio.gather(
        run_project_build_job(job_id, lease_owner="dispatch-hint-a"),
        run_project_build_job(job_id, lease_owner="dispatch-hint-b"),
    )

    assert dispatch_count == 1
    job = await _read_build_job(job_id)
    assert job.status == "succeeded"
    assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_concurrent_screenshot_claims_should_elect_single_winner(
    authenticated_client: AsyncClient,
) -> None:
    """两个协调者并发领取同一截图任务时，只有一个取得租约。"""

    job_id = await _create_screenshot_job(authenticated_client, name="多副本截图")
    factory = get_session_factory()
    worker_a = build_durable_worker_id()
    worker_b = build_durable_worker_id()

    async def _claim(worker_id: str) -> bool:
        async with factory() as session:
            claimed_ids = await claim_pending_jobs(
                session,
                PageScreenshotJob,
                worker_id=worker_id,
                limit=1,
                lease_seconds=300,
            )
            return job_id in claimed_ids

    first, second = await asyncio.gather(_claim(worker_a), _claim(worker_b))

    assert [first, second].count(True) == 1
    async with factory() as session:
        job = await session.get(PageScreenshotJob, job_id)
        assert job is not None
        assert job.status == "running"
        assert job.attempt_count == 1
        assert job.worker_id in {worker_a, worker_b}
        assert job.lease_expires_at is not None


@pytest.mark.asyncio
async def test_screenshot_claim_specific_should_reject_second_owner(
    authenticated_client: AsyncClient,
) -> None:
    """队列循环与请求内等待路径竞争时，已领取任务不得被第二执行者再次领取。"""

    job_id = await _create_screenshot_job(authenticated_client, name="截图防重复")
    factory = get_session_factory()

    async with factory() as session:
        owner = PageScreenshotJobService(session, worker_id="queue-worker")
        assert await owner._claim_specific_pending_job(job_id)

    async with factory() as session:
        waiter = PageScreenshotJobService(session, worker_id="waiter-worker")
        assert await waiter._claim_specific_pending_job(job_id) is False

    async with factory() as session:
        job = await session.get(PageScreenshotJob, job_id)
        assert job is not None
        assert job.status == "running"
        assert job.worker_id == "queue-worker"
        assert job.attempt_count == 1
