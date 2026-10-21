"""文件功能：验证 External 异步截图任务的能力门禁、临时选择器与默认指针隔离。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.enums import RecordStatus, UserRole
from app.models.page import Page
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.user import User
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.preview_size_preset import build_default_preview_size_presets
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_job_service import PageScreenshotJobService
from app.services.page_screenshot_service import PageScreenshotCaptureArtifact

FAKE_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_SHOT"
FAKE_SHA = hashlib.sha256(FAKE_PNG).hexdigest()


async def _seed_page(session, *, suffix: str) -> tuple[int, int, int, str]:
    """创建独立工作空间、页面与具备截图 Scope 的 PAT。"""

    user = User(
        username=f"screenshot-job-user-{suffix}",
        password_hash="hash",
        display_name="Screenshot Job User",
        role=UserRole.WORKSPACE_USER.value,
        preview_size_presets=build_default_preview_size_presets(),
    )
    session.add(user)
    await session.flush()
    workspace = Workspace(
        code=f"ws-shot-job-{suffix}",
        name="Screenshot Job Space",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    session.add(workspace)
    await session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
            status=RecordStatus.ACTIVE.value,
        )
    )
    project = Project(
        workspace_id=workspace.id,
        code=f"proj-shot-job-{suffix}",
        name="Screenshot Job Project",
        theme_config_yaml="{}",
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    session.add(project)
    await session.flush()
    page = Page(
        workspace_id=workspace.id,
        project_id=project.id,
        code=f"page-{suffix}",
        title="Motion Page",
        page_content="<template><div>motion</div></template>",
        current_version_no=1,
        created_by=user.id,
        updated_by=user.id,
        status=RecordStatus.ACTIVE.value,
    )
    session.add(page)
    await session.flush()
    token = (
        await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name=f"Screenshot-Job-PAT-{suffix}",
                workspace_ids=[workspace.id],
                scopes=["page:read", "preview:run"],
                expires_in_days=30,
            ),
        )
    ).token
    await session.commit()
    return page.id, workspace.id, user.id, token


@pytest.mark.asyncio
async def test_external_screenshot_job_rejects_closed_timeline_capability(client: AsyncClient) -> None:
    """时间轴临时截图能力关闭时返回稳定 409，不丢失选择器后静默执行。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        page_id, workspace_id, _user_id, token = await _seed_page(session, suffix="closed")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(workspace_id),
        "Idempotency-Key": "closed-motion-job-1",
    }
    response = await client.post(
        f"/api/v1/pages/{page_id}/screenshot-jobs",
        headers=headers,
        json={
            "motion_snapshot": {
                "timeline_id": "intro",
                "at_label": "detail",
                "offset_ms": 600,
                "visual_mode": "full",
            }
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "TIMELINE_UNSUPPORTED"
    async with session_factory() as session:
        assert (await session.scalars(select(PageScreenshotJob))).all() == []


@pytest.mark.asyncio
async def test_external_screenshot_job_status_and_content(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """临时任务成功后内容可读，且不修改页面默认截图指针。"""

    from app.schemas import timeline as timeline_schema

    monkeypatch.setattr(timeline_schema, "TIMELINE_CAPTURE_SNAPSHOT_ENABLED", True)
    monkeypatch.setattr(ObjectStorageService, "local_root", property(lambda self: tmp_path))
    session_factory = get_session_factory()
    async with session_factory() as session:
        page_id, workspace_id, _user_id, token = await _seed_page(session, suffix="temp")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-ID": str(workspace_id),
        "Idempotency-Key": "temp-motion-job-1",
    }
    created = await client.post(
        f"/api/v1/pages/{page_id}/screenshot-jobs",
        headers=headers,
        json={"motion_snapshot": {"timeline_id": "intro", "at_ms": 1200}},
    )
    assert created.status_code == 202
    created_body = created.json()
    job_id = created_body["job_id"]
    assert created_body["status"] == "pending"
    assert created_body["motion_snapshot"] == {
        "visual_mode": "full",
        "timeline_id": "intro",
        "at_ms": 1200,
    }

    async with session_factory() as session:
        job_record = await session.get(PageScreenshotJob, job_id)
        assert job_record is not None
        config_hash = job_record.config_hash
        version_no = job_record.target_page_version_no
        width = job_record.viewport_width
        height = job_record.viewport_height
    storage_key = f"page-screenshots/{page_id}/objects/{FAKE_SHA}.png"
    target = tmp_path / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(FAKE_PNG)
    artifact = PageScreenshotCaptureArtifact(
        storage_key=storage_key,
        page_version_no=version_no,
        config_hash=config_hash,
        viewport_width=width,
        viewport_height=height,
        sha256=FAKE_SHA,
        applied_motion={
            "status": "applied",
            "timeline_id": "intro",
            "plan_digest": "fnv1a-test",
            "sampled_time_ms": 1200,
            "state_digest": "state-test",
            "visual_mode": "full",
        },
    )
    async with session_factory() as session:
        service = PageScreenshotJobService(session, worker_id="test-worker")
        claimed = await service.claim_pending_jobs(limit=1)
        assert [job.id for job in claimed] == [job_id]
        monkeypatch.setattr(
            "app.services.page_screenshot_job_service.PageScreenshotService.capture_page_screenshot_artifact",
            AsyncMock(return_value=artifact),
        )
        await service.run_claimed_job(job_id, worker_id="test-worker")

    async with session_factory() as session:
        job = await session.get(PageScreenshotJob, job_id)
        assert job is not None and job.status == "succeeded"
        assert job.result_sha256 == FAKE_SHA
        assert job.result_applied_motion_json["status"] == "applied"
        page = await session.get(Page, page_id)
        assert page is not None and page.screenshot_storage_key is None

    status_response = await client.get(
        f"/api/v1/pages/{page_id}/screenshot-jobs/{job_id}", headers=headers
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["result"]["screenshot_id"] == FAKE_SHA
    assert status_body["result"]["content_url"].endswith(f"/pages/{page_id}/screenshot-jobs/{job_id}/content")
    assert status_body["result"]["applied_motion"]["sampled_time_ms"] == 1200

    content_response = await client.get(
        f"/api/v1/pages/{page_id}/screenshot-jobs/{job_id}/content", headers=headers
    )
    assert content_response.status_code == 200
    assert content_response.headers["etag"].strip('"') == FAKE_SHA
    assert content_response.content == FAKE_PNG

    # 重复创建同一选择器应复用活动任务；已成功任务不会因重放再次执行。
    replay = await client.post(
        f"/api/v1/pages/{page_id}/screenshot-jobs",
        headers={**headers, "Idempotency-Key": "temp-motion-job-1"},
        json={"motion_snapshot": {"timeline_id": "intro", "at_ms": 1200}},
    )
    assert replay.status_code == 202
    assert replay.json()["job_id"] == job_id
