"""文件功能：验证页面截图指纹会随平台字体版本变化而失效。"""

from app.schemas.project_app_config import ProjectAppPageConfig
from app.services import page_screenshot_fingerprint_service as fingerprint_module
from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService


def test_screenshot_fingerprint_should_include_platform_font_revision(monkeypatch) -> None:
    """平台字体二进制升级后，即使主题配置不变也必须生成新的截图指纹。"""

    page_config = ProjectAppPageConfig()
    original_hash = PageScreenshotFingerprintService.build_hash(
        page_config=page_config,
        theme_key="lightblue",
        theme_config={"typography": {"headingfont": "platform-sans"}},
    )

    monkeypatch.setattr(fingerprint_module, "PLATFORM_FONT_REVISION", "next-platform-font-revision")
    changed_hash = PageScreenshotFingerprintService.build_hash(
        page_config=page_config,
        theme_key="lightblue",
        theme_config={"typography": {"headingfont": "platform-sans"}},
    )

    assert changed_hash != original_hash
