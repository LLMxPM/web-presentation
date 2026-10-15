"""文件功能：统一生成页面截图的版本化公开访问地址。"""

from app.core.time_utils import normalize_utc
from app.models.page import Page


def build_page_screenshot_url(page: Page, backend_public_base_url: str) -> str | None:
    """根据页面截图指针生成受保护的截图访问地址 (W08,W11)；无截图时返回 None。"""

    if page.screenshot_storage_key is None:
        return None

    screenshot_id = "latest"
    if page.screenshot_updated_at is not None:
        screenshot_id = str(int(normalize_utc(page.screenshot_updated_at).timestamp() * 1000))

    return (
        f"{backend_public_base_url.rstrip('/')}"
        f"/api/pages/{page.id}/screenshots/{screenshot_id}/content"
    )

