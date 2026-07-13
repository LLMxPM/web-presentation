"""文件功能：验证页面渲染诊断脚本及 BrowserContext 清理规则。"""

import pytest

from app.services.capture_viewport_resolver import CaptureViewport
from app.services.page_render_diagnostics_service import PageRenderDiagnosticsService


def test_render_diagnostics_script_should_support_route_and_standalone_roots() -> None:
    """底部溢出检测应同时支持路由页和单页模块预览的根节点。"""

    script = PageRenderDiagnosticsService._build_bottom_overflow_script()

    assert ".runtime-page-print-source" in script
    assert ".runtime-view-preview-source" in script


def test_diagnostics_should_close_context_when_new_page_fails() -> None:
    """诊断页创建失败也必须关闭独立 Context，避免污染复用浏览器。"""

    class FakeContext:
        """记录 Context 的关闭状态。"""

        def __init__(self) -> None:
            self.closed = False

        def new_page(self) -> object:
            """模拟 Playwright 在创建页面时失败。"""

            raise RuntimeError("browser disconnected")

        def close(self) -> None:
            """记录资源清理。"""

            self.closed = True

    class FakeBrowser:
        """提供测试用 Context。"""

        def __init__(self) -> None:
            self.context = FakeContext()

        def new_context(self, **_kwargs: object) -> FakeContext:
            """返回测试 Context。"""

            return self.context

    browser = FakeBrowser()
    service = PageRenderDiagnosticsService()

    with pytest.raises(RuntimeError, match="disconnected"):
        service._diagnose_preview_with_browser(
            browser,
            service._build_browser_target("http://127.0.0.1:7373/__preview"),
            CaptureViewport(width=1280, height=720),
            timeout_ms=1,
            visual_ready_timeout_ms=1,
        )
    assert browser.context.closed
