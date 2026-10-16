"""文件功能：统一生成页面截图按内容版本寻址的受保护访问地址。"""

from app.models.page import Page
from app.services.screenshot_artifact_service import screenshot_content_id


def build_page_screenshot_url(page: Page, backend_public_base_url: str) -> str | None:
    """根据页面截图指针生成受保护的截图访问地址 (W08,W11)；无截图时返回 None。"""

    if page.screenshot_storage_key is None:
        return None

    screenshot_id = screenshot_content_id(page)

    return (
        f"{backend_public_base_url.rstrip('/')}"
        f"/api/pages/{page.id}/screenshots/{screenshot_id}/content"
    )

