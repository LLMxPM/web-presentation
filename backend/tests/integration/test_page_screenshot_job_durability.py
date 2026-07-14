"""文件功能：验证截图持久化任务的版本隔离、最终写入重试和失租保护。"""

from __future__ import annotations

import asyncio
import sqlite3

from httpx import AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.page_screenshot_job_service import (
    PAGE_SCREENSHOT_JOB_STALE_CODE,
    PageScreenshotJobService,
    run_page_screenshot_job,
)
from app.services.page_preview_service import PagePreviewResult


async def _create_screenshot_page(client: AsyncClient, name: str) -> dict[str, object]:
    """创建截图持久化任务测试所需的工作空间、项目和 Vue 页面。"""

    workspace_response = await client.post("/api/workspaces", json={"name": f"{name}空间", "status": "active"})
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": f"{name}项目", "status": "active"},
    )
    assert project_response.status_code == 200
    page_response = await client.post(
        "/api/pages",
        json={
            "page_content": f"<template><div>{name}</div></template>",
            "file_type": "vue",
            "title": name,
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_response.json()["id"],
        },
    )
    assert page_response.status_code == 200
    return page_response.json()


def _install_capture_stubs(monkeypatch, *, capture_callback=None) -> None:  # noqa: ANN001
    """安装不依赖 Runtime/Chromium 的预览、截图和对象存储替身。"""

    async def fake_create_page_preview(  # noqa: ANN001, ARG001
        self,
        page,
        user_id,
        *,
        asset_delivery_mode="public",
        asset_base_url_override=None,
    ) -> PagePreviewResult:
        return PagePreviewResult(
            file_path=f"src/views/{page.code}.vue",
            preview_url=f"http://runtime.local/__preview?job={page.id}",
        )

    async def fake_capture_preview(  # noqa: ANN001, ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,
    ) -> bytes:
        if capture_callback is not None:
            capture_callback(preview_url, viewport)
        return b"durable-screenshot"

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ANN001, ARG001
        return storage_key

    monkeypatch.setattr("app.services.page_screenshot_service.PagePreviewService.create_page_preview", fake_create_page_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.BrowserCaptureService.capture_preview", fake_capture_preview)
    monkeypatch.setattr("app.services.page_screenshot_service.ObjectStorageService.put_object", fake_put_object)


async def _claim_job(job_id: int) -> str:
    """以独立 Worker 标识认领指定截图任务，并返回实际拥有者。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = PageScreenshotJobService(session, worker_id="screenshot-durability-test")
        assert await service._claim_specific_pending_job(job_id)
        job = await service.get_job_by_id(job_id)
        assert job.worker_id
        return str(job.worker_id)


async def test_screenshot_job_final_sqlite_retry_should_not_recapture(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """最终页面写入临时 BUSY 时只能重试短事务，不能重复执行 Chromium 捕获。"""

    page = await _create_screenshot_page(authenticated_client, "SQLite 最终写入")
    capture_count = 0

    def on_capture(_: str, __: CaptureViewport) -> None:
        """记录截图次数。"""

        nonlocal capture_count
        capture_count += 1

    _install_capture_stubs(monkeypatch, capture_callback=on_capture)
    job_response = await authenticated_client.post(f"/api/pages/{page['id']}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    job_id = int(job_response.json()["id"])
    worker_id = await _claim_job(job_id)

    original_execute = AsyncSession.execute
    injected = False

    async def flaky_execute(self, statement, *args, **kwargs):  # noqa: ANN001
        """仅让首次 Page 最终 UPDATE 返回 SQLite BUSY。"""

        nonlocal injected
        table = getattr(statement, "table", None)
        if not injected and getattr(table, "name", None) == "pages":
            injected = True
            raise OperationalError("UPDATE pages", {}, sqlite3.OperationalError("database is locked"))
        return await original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", flaky_execute)
    await run_page_screenshot_job(job_id, worker_id=worker_id, session_factory=get_session_factory())

    status_response = await authenticated_client.get(f"/api/page-screenshot-jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"
    assert injected is True
    assert capture_count == 1


async def test_screenshot_job_should_skip_stale_page_version_before_capture(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面版本在排队期间变化时，旧任务必须跳过且不能发布或捕获旧截图。"""

    page = await _create_screenshot_page(authenticated_client, "过期截图任务")
    capture_count = 0

    def on_capture(_: str, __: CaptureViewport) -> None:
        """记录是否错误进入了截图浏览器链路。"""

        nonlocal capture_count
        capture_count += 1

    _install_capture_stubs(monkeypatch, capture_callback=on_capture)
    job_response = await authenticated_client.post(f"/api/pages/{page['id']}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    job_data = job_response.json()
    assert job_data["target_page_version_no"] == 1

    update_response = await authenticated_client.patch(
        f"/api/pages/{page['id']}",
        json={
            "page_content": "<template><div>v2</div></template>",
            "file_type": "vue",
            "change_note": "测试截图任务版本失效",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_version_no"] == 2

    worker_id = await _claim_job(int(job_data["id"]))
    await run_page_screenshot_job(int(job_data["id"]), worker_id=worker_id, session_factory=get_session_factory())

    status_response = await authenticated_client.get(f"/api/page-screenshot-jobs/{job_data['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "skipped"
    assert status_response.json()["error_code"] == PAGE_SCREENSHOT_JOB_STALE_CODE
    assert capture_count == 0

    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.status_code == 200
    assert page_response.json()["screenshot_url"] is None


async def test_screenshot_job_should_skip_when_page_changes_during_capture(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """最终提交必须再次核对目标版本，避免捕获期间页面修改后发布旧对象。"""

    page = await _create_screenshot_page(authenticated_client, "捕获中变更截图任务")
    _install_capture_stubs(monkeypatch)
    job_response = await authenticated_client.post(f"/api/pages/{page['id']}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    job_id = int(job_response.json()["id"])
    worker_id = await _claim_job(job_id)
    capture_count = 0

    async def fake_capture_during_page_update(  # noqa: ANN001, ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,
    ) -> bytes:
        """在截图对象生成前模拟另一请求保存页面新版本。"""

        nonlocal capture_count
        capture_count += 1
        update_response = await authenticated_client.patch(
            f"/api/pages/{page['id']}",
            json={
                "page_content": "<template><div>capture-race-v2</div></template>",
                "file_type": "vue",
                "change_note": "截图捕获期间更新页面",
            },
        )
        assert update_response.status_code == 200
        return b"stale-capture"

    monkeypatch.setattr(
        "app.services.page_screenshot_service.BrowserCaptureService.capture_preview",
        fake_capture_during_page_update,
    )
    await run_page_screenshot_job(job_id, worker_id=worker_id, session_factory=get_session_factory())

    status_response = await authenticated_client.get(f"/api/page-screenshot-jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "skipped"
    assert status_response.json()["error_code"] == PAGE_SCREENSHOT_JOB_STALE_CODE
    assert capture_count == 1

    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.status_code == 200
    assert page_response.json()["current_version_no"] == 2
    assert page_response.json()["screenshot_url"] is None


async def test_screenshot_job_should_skip_when_display_config_changes_during_capture(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面版本未变但展示配置变化时，最终发布也不得覆盖新配置下的截图指针。"""

    page = await _create_screenshot_page(authenticated_client, "捕获中变更展示配置")
    _install_capture_stubs(monkeypatch)
    job_response = await authenticated_client.post(f"/api/pages/{page['id']}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    job_id = int(job_response.json()["id"])
    worker_id = await _claim_job(job_id)

    async def fake_capture_during_config_update(  # noqa: ANN001, ARG001
        self,
        preview_url: str,
        viewport: CaptureViewport,
        *,
        extra_http_headers=None,
    ) -> bytes:
        """在截图捕获过程中提交新的项目展示配置。"""

        update_response = await authenticated_client.patch(
            f"/api/projects/{page['project_id']}",
            json={"page_width": 1366, "page_height": 768},
        )
        assert update_response.status_code == 200
        return b"stale-config-capture"

    monkeypatch.setattr(
        "app.services.page_screenshot_service.BrowserCaptureService.capture_preview",
        fake_capture_during_config_update,
    )
    await run_page_screenshot_job(job_id, worker_id=worker_id, session_factory=get_session_factory())

    status_response = await authenticated_client.get(f"/api/page-screenshot-jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "skipped"
    assert status_response.json()["error_code"] == PAGE_SCREENSHOT_JOB_STALE_CODE

    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.status_code == 200
    assert page_response.json()["current_version_no"] == 1
    assert page_response.json()["screenshot_url"] is None


async def test_screenshot_job_should_not_publish_artifact_after_lease_lost(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """心跳确认失租后，即使截图对象已生成也不得修改页面截图元数据。"""

    page = await _create_screenshot_page(authenticated_client, "失租截图任务")
    lease_lost = asyncio.Event()

    def on_capture(_: str, __: CaptureViewport) -> None:
        """模拟截图期间心跳发现当前 Worker 已失去租约。"""

        lease_lost.set()

    _install_capture_stubs(monkeypatch, capture_callback=on_capture)
    job_response = await authenticated_client.post(f"/api/pages/{page['id']}/screenshot-jobs", json={})
    assert job_response.status_code == 200
    job_id = int(job_response.json()["id"])
    worker_id = await _claim_job(job_id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = PageScreenshotJobService(session, worker_id=worker_id)
        await service.run_claimed_job(job_id, worker_id=worker_id, lease_lost=lease_lost)
        session.expire_all()
        job = await service.get_job_by_id(job_id)
        page_model = await service.page_service._get_page_or_raise(int(page["id"]))
        assert job.status == "running"
        assert page_model.screenshot_storage_key is None
