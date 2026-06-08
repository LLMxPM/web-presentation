"""文件功能：验证浏览器截图服务的请求头隔离规则，避免预览鉴权头污染跨源资源请求。"""

from app.services.browser_capture_service import BrowserCaptureService


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
