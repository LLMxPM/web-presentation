"""文件功能：验证 Runtime 构建任务令牌鉴权、跨任务越权拦截、Attempt/租约围栏及全局凭证边界。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.services.token_service import TokenService
from tests.integration.test_project_build import create_active_project
from tests.integration.test_project_build_job_lease import _create_build_job


def _make_build_token(
    *,
    job_id: int,
    artifact_id: str,
    project_id: int,
    workspace_id: int,
    base_url: str = "./",
    attempt_id: str | None = "att-1",
    lease_owner: str | None = "worker-1",
    expires_in_seconds: int = 900,
) -> str:
    """快速生成带有指定 claims 的构建命令令牌。"""
    return TokenService.generate_runtime_build_command_token(
        job_id=job_id,
        artifact_id=artifact_id,
        project_id=project_id,
        workspace_id=workspace_id,
        base_url=base_url,
        attempt_id=attempt_id,
        lease_owner=lease_owner,
        expires_in_seconds=expires_in_seconds,
    )


@pytest.mark.asyncio
async def test_build_worker_credential_boundaries(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证领取构建任务时的全局凭证校验：缺失、非法及有效鉴权。"""

    monkeypatch.setattr(get_settings(), "runtime_build_worker_credential", "test-secret-cred")

    # 1. 缺失凭证 -> 401 RUNTIME_BUILD_WORKER_CREDENTIAL_REQUIRED
    resp = await client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "worker-1"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "RUNTIME_BUILD_WORKER_CREDENTIAL_REQUIRED"

    # 2. 非法凭证 -> 401 RUNTIME_BUILD_WORKER_CREDENTIAL_INVALID
    resp = await client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "worker-1"},
        headers={"Authorization": "Bearer wrong-secret"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "RUNTIME_BUILD_WORKER_CREDENTIAL_INVALID"

    # 3. 正确凭证 -> 200 OK（返回无任务响应）
    resp = await client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "worker-1"},
        headers={"Authorization": "Bearer test-secret-cred"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_build_token_missing_should_return_401(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺失构建令牌调用 renew、complete、artifact 上传均返回 401。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])

    # renew 缺失 token
    resp = await client.post(f"/internal/runtime/build-jobs/{job_id}/renew")
    assert resp.status_code == 401
    assert resp.json()["code"] == "BUILD_TOKEN_REQUIRED"

    # complete 缺失 token
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/complete",
        json={"success": True},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "BUILD_TOKEN_REQUIRED"

    # artifact 缺失 token
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={"x-runtime-build-archive-entry-file": "index.html"},
        content=b"test-zip-content",
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "BUILD_TOKEN_REQUIRED"


@pytest.mark.asyncio
async def test_build_token_invalid_or_expired_should_return_401(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非法或过期构建令牌调用端点均返回 401 BUILD_TOKEN_INVALID。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])
    artifact_id = str(job_payload["snapshot_release_id"])

    # 1. 结构完全非法的 token
    bad_token_header = {"Authorization": "Bearer not-a-valid-jwt-token"}
    resp = await client.post(f"/internal/runtime/build-jobs/{job_id}/renew", headers=bad_token_header)
    assert resp.status_code == 401
    assert resp.json()["code"] == "BUILD_TOKEN_INVALID"

    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/complete",
        json={"success": True},
        headers=bad_token_header,
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "BUILD_TOKEN_INVALID"

    # 2. 已过期的 token（expires_in_seconds 为负数）
    expired_token = _make_build_token(
        job_id=job_id,
        artifact_id=artifact_id,
        project_id=project_id,
        workspace_id=workspace_id,
        expires_in_seconds=-10,
    )
    expired_header = {"Authorization": f"Bearer {expired_token}"}
    resp = await client.post(f"/internal/runtime/build-jobs/{job_id}/renew", headers=expired_header)
    assert resp.status_code == 401
    assert resp.json()["code"] == "BUILD_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_cross_job_token_abuse_rejected_403(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任务 A 签发的令牌尝试操作任务 B 时，严格返回 403 BUILD_JOB_MISMATCH。"""

    ws1_id, p1_id = await create_active_project(authenticated_client)
    ws2_id, p2_id = await create_active_project(authenticated_client)

    job_a_payload = await _create_build_job(authenticated_client, ws1_id, p1_id, monkeypatch)
    job_b_payload = await _create_build_job(authenticated_client, ws2_id, p2_id, monkeypatch)

    job_a_id = int(job_a_payload["id"])
    job_b_id = int(job_b_payload["id"])
    artifact_a_id = str(job_a_payload["snapshot_release_id"])

    # 设 job_a 和 job_b 均为 running 状态
    async with get_session_factory()() as session:
        job_a = await session.get(ProjectBuildJob, job_a_id)
        job_b = await session.get(ProjectBuildJob, job_b_id)
        assert job_a is not None and job_b is not None
        job_a.status = "running"
        job_a.attempt_id = "att-a"
        job_a.lease_owner = "worker-a"
        job_b.status = "running"
        job_b.attempt_id = "att-b"
        job_b.lease_owner = "worker-b"
        await session.commit()

    token_for_job_a = _make_build_token(
        job_id=job_a_id,
        artifact_id=artifact_a_id,
        project_id=p1_id,
        workspace_id=ws1_id,
        attempt_id="att-a",
        lease_owner="worker-a",
    )
    headers = {"Authorization": f"Bearer {token_for_job_a}"}

    # 尝试用 job_a 的令牌去续租 job_b
    resp = await client.post(f"/internal/runtime/build-jobs/{job_b_id}/renew", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUILD_JOB_MISMATCH"

    # 尝试用 job_a 的令牌去完成 job_b
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_b_id}/complete",
        json={"success": False, "error_message": "cross-abuse"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUILD_JOB_MISMATCH"

    # 尝试用 job_a 的令牌去上传 job_b 的产物
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_b_id}/artifact",
        headers={
            "Authorization": f"Bearer {token_for_job_a}",
            "x-runtime-build-archive-entry-file": "index.html",
        },
        content=b"fake-zip",
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUILD_JOB_MISMATCH"


@pytest.mark.asyncio
async def test_token_artifact_and_project_mismatch_rejected_403(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """令牌声明的 artifact_id 或 project_id 与当前任务不符时返回 403。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])
    real_artifact_id = str(job_payload["snapshot_release_id"])

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempt_id = "attempt-1"
        job.lease_owner = "worker-1"
        await session.commit()

    # 1. artifact_id 不匹配 -> 403 BUILD_ARTIFACT_MISMATCH
    token_wrong_artifact = _make_build_token(
        job_id=job_id,
        artifact_id="rel-wrong-9999",
        project_id=project_id,
        workspace_id=workspace_id,
        attempt_id="attempt-1",
        lease_owner="worker-1",
    )
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/renew",
        headers={"Authorization": f"Bearer {token_wrong_artifact}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUILD_ARTIFACT_MISMATCH"

    # 2. project_id 不匹配（上传产物端点校验） -> 403 BUILD_PROJECT_MISMATCH
    token_wrong_project = _make_build_token(
        job_id=job_id,
        artifact_id=real_artifact_id,
        project_id=999999,
        workspace_id=workspace_id,
        attempt_id="attempt-1",
        lease_owner="worker-1",
    )
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={
            "Authorization": f"Bearer {token_wrong_project}",
            "x-runtime-build-archive-entry-file": "index.html",
        },
        content=b"fake-content",
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUILD_PROJECT_MISMATCH"


@pytest.mark.asyncio
async def test_token_attempt_and_lease_owner_mismatch_rejected_409(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """令牌的 attempt_id 或 lease_owner 与当前任务不一致时返回 409。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])
    artifact_id = str(job_payload["snapshot_release_id"])

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempt_id = "attempt-current"
        job.lease_owner = "worker-current"
        await session.commit()

    # 1. attempt_id 属于旧代次（不匹配） -> 409 BUILD_ATTEMPT_MISMATCH
    token_old_attempt = _make_build_token(
        job_id=job_id,
        artifact_id=artifact_id,
        project_id=project_id,
        workspace_id=workspace_id,
        attempt_id="attempt-stale-old",
        lease_owner="worker-current",
    )
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/renew",
        headers={"Authorization": f"Bearer {token_old_attempt}"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "BUILD_ATTEMPT_MISMATCH"

    # 2. lease_owner 被其它 Worker 冒用（不匹配） -> 409 BUILD_LEASE_OWNER_MISMATCH
    token_wrong_owner = _make_build_token(
        job_id=job_id,
        artifact_id=artifact_id,
        project_id=project_id,
        workspace_id=workspace_id,
        attempt_id="attempt-current",
        lease_owner="worker-imposter",
    )
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/renew",
        headers={"Authorization": f"Bearer {token_wrong_owner}"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "BUILD_LEASE_OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_token_missing_lease_owner_should_return_403_on_renew(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """令牌缺少 lease_owner 调用 renew 时返回 403 BUILD_LEASE_OWNER_REQUIRED。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    job_payload = await _create_build_job(authenticated_client, workspace_id, project_id, monkeypatch)
    job_id = int(job_payload["id"])
    artifact_id = str(job_payload["snapshot_release_id"])

    async with get_session_factory()() as session:
        job = await session.get(ProjectBuildJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempt_id = "attempt-1"
        job.lease_owner = None
        await session.commit()

    token_without_owner = _make_build_token(
        job_id=job_id,
        artifact_id=artifact_id,
        project_id=project_id,
        workspace_id=workspace_id,
        attempt_id="attempt-1",
        lease_owner=None,
    )
    resp = await client.post(
        f"/internal/runtime/build-jobs/{job_id}/renew",
        headers={"Authorization": f"Bearer {token_without_owner}"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "BUILD_LEASE_OWNER_REQUIRED"
