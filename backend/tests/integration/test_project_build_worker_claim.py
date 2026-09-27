"""文件功能：验证 Runtime Build Worker 通过 claim/renew/complete API 领取并收尾构建任务。"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.services.project_build_service import ProjectBuildService
from app.services.token_service import TokenService
from httpx import AsyncClient
from sqlalchemy import text

from tests.integration.test_project_build import (
    build_fake_snapshot,
    build_zip_bytes,
    create_active_project,
)


@pytest.fixture
def build_worker_credential(monkeypatch) -> str:
    """注入测试用 Runtime Build Worker 共享凭证。"""

    credential = "test-build-worker-credential"
    monkeypatch.setenv("RUNTIME_BUILD_WORKER_CREDENTIAL", credential)
    get_settings.cache_clear()
    yield credential
    get_settings.cache_clear()


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
            archive_content=build_zip_bytes({"index.html": b"<html>ok</html>"}),
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

    monkeypatch.delenv("RUNTIME_BUILD_WORKER_CREDENTIAL", raising=False)
    get_settings.cache_clear()

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
async def test_claim_build_token_should_cover_total_deadline(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """attempt 令牌 TTL 必须覆盖总 deadline，否则 renew/upload/complete 会在长任务中途集体过期。"""

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

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200
    build_token = claim_response.json()["build_token"]
    assert build_token

    settings = get_settings()
    claims = TokenService.verify_runtime_build_command_token(build_token)
    ttl_seconds = int(claims["exp"]) - int(claims["iat"])
    assert ttl_seconds >= settings.project_build_total_deadline_seconds
    assert ttl_seconds >= settings.project_build_lease_seconds


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
