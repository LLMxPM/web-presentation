"""文件功能：验证页面截图任务服务的 Session 刷新边界与队列结果读取行为。"""

from types import SimpleNamespace

import pytest

from app.services.page_screenshot_job_service import PageScreenshotJobService


@pytest.mark.asyncio
async def test_ensure_latest_page_screenshot_refreshes_only_target_page() -> None:
    """截图 Worker 完成后只刷新目标页面，不能让同 Session 的附件等对象整体过期。"""

    target_page = SimpleNamespace(
        id=339,
        current_version_no=3,
        screenshot_storage_key="screenshots/page-339.png",
    )
    job = SimpleNamespace(id=333)
    terminal = SimpleNamespace(status="succeeded")
    result = SimpleNamespace(page=target_page, refreshed=True)

    class FakeSession:
        def __init__(self) -> None:
            self.refreshed: list[object] = []
            self.committed = False

        async def commit(self) -> None:
            self.committed = True

        async def refresh(self, instance: object) -> None:
            self.refreshed.append(instance)

        def expire_all(self) -> None:
            pytest.fail("截图刷新不应使共享 Session 中的全部 ORM 对象过期")

    class FakePageService:
        async def _get_page_or_raise(self, page_id: int):
            assert page_id == 339
            return target_page

    class FakeScreenshotService:
        def __init__(self) -> None:
            self.screenshot_fingerprint_service = SimpleNamespace(build_page_snapshot=self.build_page_snapshot)
            self.viewport_resolver = SimpleNamespace(resolve=lambda current_page, project_page_config: "viewport")

        @staticmethod
        def _validate_page_screenshot_supported(current_page: object) -> None:
            assert current_page is target_page

        @staticmethod
        def _ensure_page_within_scope(current_page: object, **kwargs) -> None:  # noqa: ANN003
            assert current_page is target_page
            assert kwargs == {"workspace_id": 9, "project_id": 55}

        @staticmethod
        async def build_page_snapshot(current_page: object):
            assert current_page is target_page
            return SimpleNamespace(page_config={}, config_hash="config-hash")

        @staticmethod
        async def _build_result(*, page: object, content: bytes, refreshed: bool):
            assert (page, content, refreshed) == (target_page, b"png-content", True)
            return result

    class FakeObjectStorageService:
        @staticmethod
        async def read_object(storage_key: str) -> bytes:
            assert storage_key == "screenshots/page-339.png"
            return b"png-content"

    session = FakeSession()
    service = PageScreenshotJobService.__new__(PageScreenshotJobService)
    service.session = session
    service.page_service = FakePageService()
    service.screenshot_service = FakeScreenshotService()
    service.object_storage_service = FakeObjectStorageService()
    service.settings = SimpleNamespace(page_screenshot_ai_wait_timeout_seconds=90)

    async def try_build_current_result(current_page: object):
        assert current_page is target_page
        return None

    async def get_or_create_job(**kwargs):  # noqa: ANN003
        assert kwargs["page"] is target_page
        assert kwargs["target_page_version_no"] == 3
        return job

    async def wait_for_job_terminal_detached(job_id: int, **kwargs):  # noqa: ANN003
        assert job_id == 333
        assert kwargs == {"timeout_seconds": 90}
        return terminal

    service._try_build_current_result = try_build_current_result
    service._get_or_create_job = get_or_create_job
    service.wait_for_job_terminal_detached = wait_for_job_terminal_detached
    service._raise_if_job_stale = lambda current_terminal: None

    actual = await service.ensure_latest_page_screenshot_via_queue(
        page_id=339,
        user_id=1,
        workspace_id=9,
        project_id=55,
    )

    assert actual is result
    assert session.committed is True
    assert session.refreshed == [target_page]
