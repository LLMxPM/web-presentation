"""文件功能：验证 Runtime Build Worker 通过 claim/renew/complete API 领取并收尾构建任务。"""

from __future__ import annotations

from datetime import datetime

import pytest
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.services.project_build_service import ProjectBuildService
from app.services.token_service import TokenService
from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.test_project_build import (
    aiter_chunks,
    build_fake_snapshot,
    build_zip_bytes,
    create_active_project,
)


@pytest.mark.asyncio
async def test_claim_renew_complete_should_drive_job_lifecycle(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """claim 领取、renew 续租、complete 上报终态应完整驱动任务生命周期。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ):
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["job_id"] == job_id
    assert claim["build_token"]
    assert claim["service_token"]
    assert claim["attempt_id"]
    assert claim["lease_owner"] == "runtime-build-test"
    build_token = claim["build_token"]

    renew_response = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/renew",
        headers={"Authorization": f"Bearer {build_token}"},
    )
    assert renew_response.status_code == 200
    assert renew_response.json()["lease_expires_at"]

    async with get_session_factory()() as session:
        service = ProjectBuildService(session)
        job = await service.get_job_by_id(job_id)
        await service.persist_uploaded_artifact(
            job=job,
            archive_chunks=aiter_chunks([build_zip_bytes({"index.html": b"<html>ok</html>"})]),
            entry_file="index.html",
            sha256=None,
            size_bytes=None,
            attempt_id=job.attempt_id,
            lease_owner=job.lease_owner,
        )

    complete_response = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/complete",
        json={"success": True},
        headers={"Authorization": f"Bearer {build_token}"},
    )
    assert complete_response.status_code == 200

    async with get_session_factory()() as session:
        finished = await session.get(ProjectBuildJob, job_id)
        assert finished is not None
        assert finished.status == "succeeded"
        assert finished.artifact_storage_key


@pytest.mark.asyncio
async def test_claim_should_reject_missing_credential(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """未配置共享凭证时 claim 应 fail-closed。"""

    # 凭证可能由开发者本地 .env 提供，只删进程环境变量无法复现「未配置」，直接清空已加载配置。
    settings = get_settings()
    monkeypatch.setattr(settings, "runtime_build_worker_credential", "")
    monkeypatch.setattr(settings, "runtime_build_worker_credential_file", "")

    response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "RUNTIME_BUILD_WORKER_CREDENTIAL_MISSING"


@pytest.mark.asyncio
async def test_claim_missing_snapshot_should_fail_job_not_requeue(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """快照缺失属于不可重试缺陷：claim 应直接 failed，禁止回到 pending 毒丸循环。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ):
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    async with get_session_factory()() as session:
        # SQLite 测试库开启外键约束：临时关闭以便植入“快照缺失”的坏引用。
        await session.execute(text("PRAGMA foreign_keys=OFF"))
        await session.execute(
            text("UPDATE project_build_jobs SET snapshot_release_id = 999999999 WHERE id = :job_id"),
            {"job_id": job_id},
        )
        await session.commit()
        await session.execute(text("PRAGMA foreign_keys=ON"))
        await session.commit()

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["build_token"] is None
    assert "失败" in claim["message"]

    async with get_session_factory()() as session:
        failed = await session.get(ProjectBuildJob, job_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.lease_owner is None


@pytest.mark.asyncio
async def test_claim_build_token_should_be_capped_by_job_deadline(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """attempt 令牌 TTL 应覆盖完整租约，但不得越过任务绝对 deadline。

    新语义下 deadline_at 是任务创建即确定的 wall-clock 上界：令牌活得比它长，
    等于让超期任务仍具备 renew/upload/complete 能力。
    """

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ):
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["deadline_at"]

    settings = get_settings()
    claims = TokenService.verify_runtime_build_command_token(claim["build_token"])
    ttl_seconds = int(claims["exp"]) - int(claims["iat"])
    # 至少覆盖一次完整租约，否则刚续上的租约会被令牌过期打断。
    assert ttl_seconds >= settings.project_build_lease_seconds
    # 不超过任务剩余期限（允许 1 秒以内的取整误差）。
    assert int(claims["exp"]) <= int(datetime.fromisoformat(claim["deadline_at"]).timestamp()) + 1

    async with get_session_factory()() as session:
        service = ProjectBuildService(session)
        job = await service.get_job_by_id(job_id)
        assert job.lease_expires_at is not None
        assert job.lease_expires_at <= job.deadline_at


@pytest.mark.asyncio
async def test_claim_near_deadline_should_cap_lease_and_token(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """排队到接近总期限的任务：租约与令牌必须裁剪到剩余预算，不得再给满额时长。"""

    from datetime import timedelta

    from app.core.time_utils import utc_now

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ):
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    remaining_seconds = 60
    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.deadline_at = utc_now() + timedelta(seconds=remaining_seconds)
        await session.commit()

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["job_id"] == job_id

    lease_expires_at = datetime.fromisoformat(str(claim["lease_expires_at"]))
    deadline_at = datetime.fromisoformat(str(claim["deadline_at"]))
    assert lease_expires_at <= deadline_at
    assert (deadline_at - lease_expires_at).total_seconds() < 1

    claims = TokenService.verify_runtime_build_command_token(claim["build_token"])
    assert int(claims["exp"]) <= int(deadline_at.timestamp()) + 1

    # 剩余预算内的租约同样无法再续：超过 deadline 后 Backend 不再承认所有权。
    async with get_session_factory()() as session:
        service = ProjectBuildService(session)
        job = await service.get_job_by_id(job_id)
        job.deadline_at = utc_now() - timedelta(seconds=1)
        await session.commit()
    async with get_session_factory()() as session:
        rejected = await ProjectBuildService(session).renew_job_lease(
            job_id=job_id,
            lease_owner="runtime-build-test",
        )
    assert rejected is None


@pytest.mark.asyncio
async def test_overdue_pending_build_job_should_fail(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """超过总期限仍未被领取的 pending 任务应收敛为 failed，避免无 Worker 时无限悬挂。"""

    from datetime import timedelta

    from app.core.time_utils import utc_now
    from app.services.project_build_service import fail_overdue_pending_build_jobs

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ):
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.deadline_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with get_session_factory()() as session:
        failed_count = await fail_overdue_pending_build_jobs(session)
    assert failed_count == 1

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert "总执行期限" in (job.error_message or "")


@pytest.mark.asyncio
async def test_claim_should_skip_overdue_pending_job(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """超过总期限的 pending 任务不得再被领取，避免与 fail_overdue 竞态拉起超期构建。"""

    from datetime import timedelta

    from app.core.time_utils import utc_now

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ):
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.deadline_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["job_id"] is None

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        assert job.status == "pending"
