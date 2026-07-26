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


def test_capture_should_reduce_motion_and_disable_animations() -> None:
    """截图必须模拟 reduced-motion 并在截图瞬间禁用残留动画，避免动画中间帧导致内容缺失。"""

    class FakePage:
        """记录截图参数的页面替身。"""

        def __init__(self) -> None:
            self.screenshot_kwargs: dict[str, object] = {}

        def route(self, *_args: object, **_kwargs: object) -> None:
            """无需路由拦截。"""

        def on(self, *_args: object, **_kwargs: object) -> None:
            """忽略事件监听注册。"""

        def goto(self, *_args: object, **_kwargs: object) -> None:
            """模拟导航成功。"""

        def wait_for_function(self, *_args: object, **_kwargs: object) -> None:
            """模拟预览就绪。"""

        def evaluate(self, script: str, *_args: object) -> object:
            """对视觉资源等待脚本返回就绪结果。"""

            if "waitForVisualAssets" in script:
                return {"ok": True, "total": 0, "failed": [], "pending": []}
            return None

        def wait_for_timeout(self, *_args: object) -> None:
            """跳过固定等待。"""

        def screenshot(self, **kwargs: object) -> bytes:
            """记录截图入参并返回图片字节。"""

            self.screenshot_kwargs = kwargs
            return b"png"

    class FakeContext:
        """返回固定页面并记录关闭状态。"""

        def __init__(self) -> None:
            self.page = FakePage()
            self.closed = False

        def new_page(self) -> FakePage:
            """返回测试页面。"""

            return self.page

        def close(self) -> None:
            """记录清理调用。"""

            self.closed = True

    class FakeBrowser:
        """记录 Context 创建参数。"""

        def __init__(self) -> None:
            self.context_options: dict[str, object] = {}
            self.context = FakeContext()

        def new_context(self, **kwargs: object) -> FakeContext:
            """记录入参并返回测试 Context。"""

            self.context_options = kwargs
            return self.context

    browser = FakeBrowser()
    service = BrowserCaptureService()

    content = service._capture_preview_with_browser(
        browser,
        "http://127.0.0.1:7373/__preview",
        CaptureViewport(width=1280, height=720),
        timeout_ms=1000,
        visual_ready_timeout_ms=1000,
    )

    assert content == b"png"
    assert browser.context_options.get("reduced_motion") == "reduce"
    assert browser.context.page.screenshot_kwargs.get("animations") == "disabled"
    assert browser.context.closed
