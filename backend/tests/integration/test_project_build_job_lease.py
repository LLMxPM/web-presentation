"""文件功能：验证项目构建任务的持久领取、attempt 身份、租约与结果围栏。"""

from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.services.project_artifact_builder import ProjectArtifactSnapshot
from app.services.project_build_service import (
    ProjectBuildService,
    recover_expired_build_jobs,
    recover_interrupted_build_jobs_on_startup,
)
from app.services.token_service import TokenService
from tests.integration.test_project_build import (
    build_fake_snapshot,
    build_zip_bytes,
    create_active_project,
)


async def _create_build_job(
    authenticated_client: AsyncClient,
    workspace_id: int,
    project_id: int,
    monkeypatch,
    *,
    max_attempts: int = 3,
) -> dict:
    """创建构建任务并返回 API 响应，同时可选覆盖重试预算。"""

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
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert response.status_code == 200
    job_payload = response.json()
    if max_attempts != 3:
        async with get_session_factory()() as session:
            job = await session.get(ProjectBuildJob, job_payload["id"])
            assert job is not None
            job.max_attempts = max_attempts
            await session.commit()
    return job_payload


@pytest.mark.asyncio
async def test_claim_job_should_set_attempt_identity_and_lease(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """领取任务后应写入新的 attempt_id、递增 attempt_count 并持有租约。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        service = ProjectBuildService(session, lease_owner="worker-a")
        claimed = await service.claim_job(job_id=job_id)

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.lease_owner == "worker-a"
    assert claimed.lease_expires_at is not None
    assert claimed.claimed_at is not None
    assert claimed.attempt_id
    assert claimed.attempt_count == 1
    assert claimed.attempt_id != job_payload.get("attempt_id")

    async with get_session_factory()() as session:
        # 同一任务不得被第二个领取者再次取得。
        other = await ProjectBuildService(session, lease_owner="worker-b").claim_job(job_id=job_id)
    assert other is None


@pytest.mark.asyncio
async def test_claim_job_should_allow_takeover_after_lease_expired(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """租约过期后任务应回到可领取状态，由新执行者接管并轮换 attempt。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        first = await ProjectBuildService(session, lease_owner="worker-a").claim_job(job_id=job_id)
        assert first is not None
        first_attempt = first.attempt_id
        first.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with get_session_factory()() as session:
        recovered = await recover_expired_build_jobs(session)
    assert recovered == 1

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.lease_owner is None

    async with get_session_factory()() as session:
        second = await ProjectBuildService(session, lease_owner="worker-b").claim_job(job_id=job_id)

    assert second is not None
    assert second.lease_owner == "worker-b"
    assert second.attempt_count == 2
    assert second.attempt_id != first_attempt


@pytest.mark.asyncio
async def test_run_project_build_job_should_requeue_then_fail_on_budget(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Worker complete 失败且未超重试预算应回到 pending，超预算后标为 failed。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(
        authenticated_client,
        workspace_id,
        project_id,
        monkeypatch,
        max_attempts=2,
    )
    job_id = job_payload["id"]

    async def claim_and_fail(worker_id: str) -> str:
        async with get_session_factory()() as session:
            service = ProjectBuildService(session, lease_owner=worker_id)
            claimed = await service.claim_job(job_id=job_id, lease_owner=worker_id)
            assert claimed is not None
            if service.is_retry_allowed(claimed):
                requeued = await service.release_job_to_pending(
                    job_id=job_id,
                    lease_owner=worker_id,
                    error_message="Runtime 暂不可用。",
                )
                assert requeued
                return "pending"
            failed = await service.complete_job(
                job_id=job_id,
                lease_owner=worker_id,
                success=False,
                error_message="Runtime 暂不可用。",
            )
            assert failed
            return "failed"

    assert await claim_and_fail("worker-a") == "pending"
    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.attempt_count == 1
        assert job.lease_owner is None
        assert job.attempt_id is None
        assert job.error_message == "Runtime 暂不可用。"

    assert await claim_and_fail("worker-b") == "failed"
    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.attempt_count == 2
        assert job.finished_at is not None


@pytest.mark.asyncio
async def test_uncertain_build_response_should_wait_for_lease_before_retry(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Worker 失联后保留 running/attempt，待租约过期才允许回收重派。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        service = ProjectBuildService(session, lease_owner="worker-a")
        claimed = await service.claim_job(job_id=job_id, lease_owner="worker-a")
        assert claimed is not None

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "running"
        assert job.attempt_count == 1
        assert job.attempt_id is not None
        assert job.lease_expires_at is not None
        assert job.lease_expires_at > utc_now()
        job.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with get_session_factory()() as session:
        assert await recover_expired_build_jobs(session) == 1
    async with get_session_factory()() as session:
        recovered = await session.get(ProjectBuildJob, job_id)
        assert recovered is not None
        assert recovered.status == "pending"
        assert recovered.attempt_id is None


@pytest.mark.asyncio
async def test_run_project_build_job_should_fail_immediately_past_deadline(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """超过总 deadline 后即使仍有重试预算也不再重试。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(
        authenticated_client,
        workspace_id,
        project_id,
        monkeypatch,
        max_attempts=5,
    )
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        service = ProjectBuildService(session, lease_owner="worker-a")
        claimed = await service.claim_job(job_id=job_id, lease_owner="worker-a")
        assert claimed is not None

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.deadline_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with get_session_factory()() as session:
        service = ProjectBuildService(session, lease_owner="worker-a")
        job = await service.get_job_by_id(job_id)
        assert not service.is_retry_allowed(job)
        failed = await service.complete_job(
            job_id=job_id,
            lease_owner="worker-a",
            success=False,
            error_message="Runtime 暂不可用。",
        )
        assert failed

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_upload_should_reject_stale_attempt_and_keep_latest_result(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """迟到上传不得覆盖新 attempt 结果；匹配 attempt 才能提升最终产物。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        service = ProjectBuildService(session, lease_owner="worker-a")
        claimed = await service.claim_job(job_id=job_id)
        assert claimed is not None
        attempt_a = claimed.attempt_id
        release_id = claimed.snapshot_release_id

    archive_a = build_zip_bytes({"index.html": b"<html>a</html>"})
    token_a = TokenService.generate_runtime_build_command_token(
        job_id=job_id,
        artifact_id=str(release_id),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="./",
        attempt_id=attempt_a,
        lease_owner="worker-a",
    )
    upload_a = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"archive": ("dist.zip", archive_a, "application/zip")},
        data={
            "entry_file": "index.html",
            "sha256": hashlib.sha256(archive_a).hexdigest(),
            "size_bytes": str(len(archive_a)),
        },
    )
    assert upload_a.status_code == 200
    assert f"/attempts/{attempt_a}/" in upload_a.json()["artifact_storage_key"]

    # 模拟失败重试：回到 pending 后由 worker-b 领取新 attempt。
    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.status = "pending"
        job.lease_owner = None
        job.lease_expires_at = None
        job.attempt_id = None
        await session.commit()

    async with get_session_factory()() as session:
        reclaimed = await ProjectBuildService(session, lease_owner="worker-b").claim_job(job_id=job_id)
        assert reclaimed is not None
        attempt_b = reclaimed.attempt_id
        assert attempt_b != attempt_a

    # 迟到的 attempt_a 上传不得覆盖。
    late_upload = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"archive": ("dist.zip", archive_a, "application/zip")},
        data={
            "entry_file": "index.html",
            "sha256": hashlib.sha256(archive_a).hexdigest(),
            "size_bytes": str(len(archive_a)),
        },
    )
    assert late_upload.status_code == 409
    assert late_upload.json()["code"] == "BUILD_ATTEMPT_MISMATCH"

    archive_b = build_zip_bytes({"index.html": b"<html>b</html>"})
    token_b = TokenService.generate_runtime_build_command_token(
        job_id=job_id,
        artifact_id=str(release_id),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="./",
        attempt_id=attempt_b,
        lease_owner="worker-b",
    )
    upload_b = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={"Authorization": f"Bearer {token_b}"},
        files={"archive": ("dist.zip", archive_b, "application/zip")},
        data={
            "entry_file": "index.html",
            "sha256": hashlib.sha256(archive_b).hexdigest(),
            "size_bytes": str(len(archive_b)),
        },
    )
    assert upload_b.status_code == 200
    assert upload_b.json()["artifact_storage_key"].endswith(f"/attempts/{attempt_b}/dist.zip")

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.attempt_id == attempt_b
        assert job.artifact_storage_key and attempt_b in job.artifact_storage_key
        assert job.artifact_sha256 == hashlib.sha256(archive_b).hexdigest()


@pytest.mark.asyncio
async def test_upload_should_reject_expired_lease(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """租约过期后，即使 attempt 匹配也不得提升产物。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="worker-a").claim_job(job_id=job_id)
        assert claimed is not None
        attempt_id = claimed.attempt_id
        release_id = claimed.snapshot_release_id
        claimed.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    archive = build_zip_bytes({"index.html": b"<html>x</html>"})
    token = TokenService.generate_runtime_build_command_token(
        job_id=job_id,
        artifact_id=str(release_id),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="./",
        attempt_id=attempt_id,
        lease_owner="worker-a",
    )
    response = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={"Authorization": f"Bearer {token}"},
        files={"archive": ("dist.zip", archive, "application/zip")},
        data={
            "entry_file": "index.html",
            "sha256": hashlib.sha256(archive).hexdigest(),
            "size_bytes": str(len(archive)),
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "BUILD_LEASE_EXPIRED"


@pytest.mark.asyncio
async def test_upload_should_reject_lease_owner_mismatch(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """非租约持有者签发的令牌不得提升产物。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="worker-a").claim_job(job_id=job_id)
        assert claimed is not None
        attempt_id = claimed.attempt_id
        release_id = claimed.snapshot_release_id

    archive = build_zip_bytes({"index.html": b"<html>x</html>"})
    token = TokenService.generate_runtime_build_command_token(
        job_id=job_id,
        artifact_id=str(release_id),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="./",
        attempt_id=attempt_id,
        lease_owner="worker-evil",
    )
    response = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={"Authorization": f"Bearer {token}"},
        files={"archive": ("dist.zip", archive, "application/zip")},
        data={
            "entry_file": "index.html",
            "sha256": hashlib.sha256(archive).hexdigest(),
            "size_bytes": str(len(archive)),
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "BUILD_LEASE_OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_recover_interrupted_build_jobs_on_startup_should_respect_budget(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """启动收敛应按重试预算回 pending 或标 failed，并作废 attempt。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(
        authenticated_client,
        workspace_id,
        project_id,
        monkeypatch,
        max_attempts=1,
    )
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="worker-a").claim_job(job_id=job_id)
        assert claimed is not None
        # 模拟租约过期后的进程中断，避免启动收敛抢走其它副本健康租约。
        claimed.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    session_factory = get_session_factory()
    recovered = await recover_interrupted_build_jobs_on_startup(session_factory)
    assert recovered == 1

    async with session_factory() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        # attempt_count=1 已达 max_attempts=1，启动收敛直接标 failed。
        assert job.status == "failed"
        assert job.attempt_id is None
        assert job.lease_owner is None


@pytest.mark.asyncio
async def test_startup_recovery_should_not_steal_healthy_lease_from_other_replica(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """任意 Backend 启动都不得重置其它副本租约仍有效的 running 构建。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="other-replica-worker").claim_job(job_id=job_id)
        assert claimed is not None
        assert claimed.lease_expires_at is not None
        assert claimed.lease_expires_at > utc_now()

    session_factory = get_session_factory()
    recovered = await recover_interrupted_build_jobs_on_startup(session_factory)
    assert recovered == 0

    async with session_factory() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "running"
        assert job.lease_owner == "other-replica-worker"
        assert job.attempt_id == claimed.attempt_id


@pytest.mark.asyncio
async def test_startup_recovery_force_owner_prefix_only_touches_matching_owner(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """force_owner_prefix 只回收本进程前缀任务，不碰其它 owner 的健康租约。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="local-host:1:abc").claim_job(job_id=job_id)
        assert claimed is not None

    session_factory = get_session_factory()
    recovered = await recover_interrupted_build_jobs_on_startup(
        session_factory,
        owner_prefix="local-host:",
    )
    assert recovered == 1

    async with session_factory() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.attempt_id is None
        assert job.lease_owner is None


@pytest.mark.asyncio
async def test_recover_expired_should_settle_success_when_artifact_present(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """回收时若产物已提升，应按成功收敛，不得清空产物再重派。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="worker-a").claim_job(job_id=job_id)
        assert claimed is not None
        claimed.lease_expires_at = utc_now() - timedelta(seconds=1)
        # 模拟「超时前产物已上传、终态未写入」的崩溃窗口。
        claimed.artifact_storage_key = "build-artifacts/1/1/attempts/x/dist.zip"
        claimed.artifact_sha256 = "abc"
        await session.commit()

    async with get_session_factory()() as session:
        recovered = await recover_expired_build_jobs(session)
    assert recovered == 1

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "succeeded"
        assert job.artifact_storage_key == "build-artifacts/1/1/attempts/x/dist.zip"
        assert job.artifact_sha256 == "abc"


@pytest.mark.asyncio
async def test_recover_expired_should_invalidate_attempt_and_artifact_metadata(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """无产物回收后 attempt_id 必须为空，且不得残留产物指针。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        claimed = await ProjectBuildService(session, lease_owner="worker-a").claim_job(job_id=job_id)
        assert claimed is not None
        claimed.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with get_session_factory()() as session:
        recovered = await recover_expired_build_jobs(session)
    assert recovered == 1

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.attempt_id is None
        assert job.artifact_storage_key is None
        assert job.artifact_sha256 is None


@pytest.mark.asyncio
async def test_assert_attempt_fence_should_reject_when_lease_owner_missing(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """无租约持有者时围栏必须拒绝，避免死 attempt 在 pending 行上提升产物。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = job_payload["id"]

    async with get_session_factory()() as session:
        service = ProjectBuildService(session, lease_owner="worker-a")
        job = await service.get_job_by_id(job_id)
        job.status = "pending"
        job.attempt_id = "dead-attempt"
        job.lease_owner = None
        job.lease_expires_at = None
        await session.commit()

        with pytest.raises(AppException) as exc_info:
            service.assert_attempt_fence(job=job, attempt_id="dead-attempt", lease_owner="worker-a")
        assert exc_info.value.code == "BUILD_LEASE_MISSING"
