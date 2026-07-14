"""文件功能：验证浏览器截图服务的请求头隔离和 BrowserContext 清理规则。"""

import pytest

from app.services.browser_capture_service import BrowserCaptureService
from app.services.capture_viewport_resolver import CaptureViewport


def test_preview_headers_should_only_attach_to_initial_preview_document() -> None:
    """仅初始 Runtime 预览文档请求需要附加截图鉴权头。"""

    assert BrowserCaptureService._should_attach_initial_preview_headers(
        request_url="http://127.0.0.1:7373/__preview",
        preview_url="http://127.0.0.1:7373/__preview",
        is_navigation_request=True,
        resource_type="document",
    )


def test_preview_headers_should_not_attach_to_cross_origin_assets() -> None:
    """跨源 Drawio CDN 和 Backend 资源请求不能携带 Runtime 预览鉴权头。"""

    assert not BrowserCaptureService._should_attach_initial_preview_headers(
        request_url="https://viewer.diagrams.net/js/viewer.min.js",
        preview_url="http://127.0.0.1:7373/__preview",
        is_navigation_request=False,
        resource_type="script",
    )
    assert not BrowserCaptureService._should_attach_initial_preview_headers(
        request_url="http://127.0.0.1:8000/public/cached-assets/1/demo",
        preview_url="http://127.0.0.1:7373/__preview",
        is_navigation_request=False,
        resource_type="fetch",
    )


def test_capture_should_close_context_when_new_page_fails() -> None:
    """页面对象创建失败时也不能泄漏长期 Chromium 槽位中的 Context。"""

    class FakeContext:
        """记录 Context 是否被关闭。"""

        def __init__(self) -> None:
            self.closed = False

        def new_page(self) -> object:
            """模拟浏览器在创建页面时断连。"""

            raise RuntimeError("browser disconnected")

        def close(self) -> None:
            """记录清理调用。"""

            self.closed = True

    class FakeBrowser:
        """返回可检查的 Context。"""

        def __init__(self) -> None:
            self.context = FakeContext()

        def new_context(self, **_kwargs: object) -> FakeContext:
            """创建测试 Context。"""

            return self.context

    browser = FakeBrowser()
    service = BrowserCaptureService()

    with pytest.raises(RuntimeError, match="disconnected"):
        service._capture_preview_with_browser(
            browser,
            "http://127.0.0.1:7373/__preview",
            CaptureViewport(width=1280, height=720),
            timeout_ms=1,
            visual_ready_timeout_ms=1,
        )
    assert browser.context.closed
