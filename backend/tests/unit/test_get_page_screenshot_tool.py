"""文件功能：验证页面截图 AI 工具返回 URL 与图片传输地址一致。"""

from types import SimpleNamespace

from app.ai.tools.page.get_page_screenshot import _build_page_screenshot_tool_content


def test_page_screenshot_tool_content_should_prefer_resolved_image_url() -> None:
    """URL 传输时，截图工具应返回模型实际可访问的对象存储地址。"""

    page = SimpleNamespace(
        id=224,
        code="PG20260520014",
        title="P13 最终交付版图",
        screenshot_version_no=4,
    )
    resolved_image = SimpleNamespace(
        transport="url",
        url="https://oss.example.com/page-screenshots/PG20260520014.png?X-Amz-Signature=demo",
    )

    content = _build_page_screenshot_tool_content(
        page=page,
        backend_public_url="http://127.0.0.1:8000/public/page-screenshots/224?v=1779334083885",
        refreshed=False,
        resolved_image=resolved_image,
    )

    assert content["screenshot_url"] == resolved_image.url
    assert content["transport"] == "url"


def test_page_screenshot_tool_content_should_fallback_backend_url_without_image_url() -> None:
    """base64 等非 URL 传输时，截图工具保留 Backend 公开入口作为展示兜底。"""

    page = SimpleNamespace(
        id=224,
        code="PG20260520014",
        title="P13 最终交付版图",
        screenshot_version_no=4,
    )
    backend_public_url = "http://127.0.0.1:8000/public/page-screenshots/224?v=1779334083885"
    resolved_image = SimpleNamespace(transport="base64", url=None)

    content = _build_page_screenshot_tool_content(
        page=page,
        backend_public_url=backend_public_url,
        refreshed=False,
        resolved_image=resolved_image,
    )

    assert content["screenshot_url"] == backend_public_url
    assert content["transport"] == "base64"
