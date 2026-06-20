"""文件功能：验证页面截图 AI 工具返回稳定预览 URL 与图片引用。"""

from types import SimpleNamespace

from app.ai.tools.page.get_page_screenshot import _build_page_screenshot_tool_content


def test_page_screenshot_tool_content_should_prefer_attachment_preview_url() -> None:
    """截图工具内容应返回登录态预览 URL，避免泄漏模型 presigned URL。"""

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
        attachment_preview_url="/api/ai/attachments/images/9/content",
        image_ref={"kind": "agent-image-ref", "attachment_id": 9, "source_kind": "tool_output"},
        refreshed=False,
        resolved_image=resolved_image,
    )

    assert content["screenshot_url"] == "/api/ai/attachments/images/9/content"
    assert content["screenshot_preview_url"] == "/api/ai/attachments/images/9/content"
    assert content["image_ref"]["attachment_id"] == 9
    assert "X-Amz-Signature" not in str(content)
    assert content["transport"] == "url"


def test_page_screenshot_tool_content_should_fallback_backend_url_without_image_url() -> None:
    """未提供附件预览 URL 时，截图工具保留 Backend 公开入口作为展示兜底。"""

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
