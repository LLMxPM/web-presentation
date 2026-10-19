"""文件功能：验证校验附图发布、候选变化拒绝、跨空间及过期对象回收。"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.page import Page
from app.models.page_screenshot_artifact import PageScreenshotArtifact
from app.services.code_check_fingerprint import CodeCheckFingerprintBuilder
from app.services.code_check_result_cache import compute_check_fingerprint
from app.services.validation_screenshot_publisher import PreparedValidationScreenshot, publish_validation_screenshot
from app.services.validation_screenshot_cleanup import cleanup_validation_screenshots
from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService


@pytest.mark.parametrize("drift", [None, "source", "title", "expired", "scope", "viewport"])
async def test_publish_only_matching_candidate(authenticated_client, drift):
    """原始候选可原子发布；源码/标题变化、跨空间或过期不得返回 ready。"""
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "截图发布测试"})).json()["id"]
    project = (await authenticated_client.post("/api/projects", json={"workspace_id": ws, "name": "截图项目"})).json()["id"]
    page_response = await authenticated_client.post("/api/pages", json={"workspace_id": ws, "project_id": project,
                "title": "正式标题", "page_content": "<template><main>正式内容</main></template>"})
    assert page_response.status_code == 200, page_response.text
    page_id = page_response.json()["id"]
    async with get_session_factory()() as session:
        page = await session.get(Page, page_id)
        base = await CodeCheckFingerprintBuilder(session).build_page_fingerprint(workspace_id=ws, project_id=project,
            source=page.page_content, importer_module_path=f"src/views/{page.code}.vue",
            page_metadata={"code": page.code, "title": page.title, "speaker_notes": page.speaker_notes})
        identity = compute_check_fingerprint({"diagnostics": base, "capture_screenshot": True, "capture_policy": "page-static-capture.v1"})
        snapshot = await PageScreenshotFingerprintService(session).build_page_snapshot(page)
        expires = utc_now() + timedelta(minutes=-1 if drift == "expired" else 10)
        artifact = PageScreenshotArtifact(artifact_id="candidate", workspace_id=ws, sha256="a" * 64,
                                         storage_key="test/candidate.png", expires_at=expires)
        session.add(artifact)
        await session.flush()
        if drift == "source":
            page.page_content = "<template><main>变化的内容</main></template>"
        if drift == "title":
            page.title = "变更标题"
        prepared = PreparedValidationScreenshot("candidate", identity, ws + 1 if drift == "scope" else ws, "a" * 64,
                        1 if drift == "viewport" else snapshot.page_config.width, snapshot.page_config.height)
        result = await publish_validation_screenshot(session, page=page, validation={}, prepared=prepared)
        assert result["status"] == ("ready" if drift is None else "pending")
        assert (page.screenshot_storage_key is not None) == (drift is None)
        await session.commit()


async def test_cleanup_only_unpublished_expired_candidates(authenticated_client, monkeypatch):
    """取消/崩溃留下的临时对象过期后回收，已发布和未过期对象继续保留。"""
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "截图回收测试"})).json()["id"]
    async with get_session_factory()() as session:
        for name, expires in (("expired", utc_now() - timedelta(seconds=1)), ("fresh", utc_now() + timedelta(minutes=1))):
            session.add(PageScreenshotArtifact(artifact_id=name, workspace_id=ws, sha256="a" * 64,
                                              storage_key=f"test/{name}.png", expires_at=expires))
        await session.commit()
    remove = AsyncMock()
    monkeypatch.setattr("app.services.validation_screenshot_cleanup.ObjectStorageService.delete_object", remove)
    assert await cleanup_validation_screenshots(get_session_factory()) == 1
    remove.assert_awaited_once_with("test/expired.png")
    async with get_session_factory()() as session:
        assert list(await session.scalars(select(PageScreenshotArtifact.artifact_id))) == ["fresh"]
