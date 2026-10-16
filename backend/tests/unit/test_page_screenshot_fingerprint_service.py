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


def test_screenshot_fingerprint_should_include_model3d_identity(monkeypatch) -> None:
    """三维引用实时身份与引擎身份必须入截图指纹：资源替换或引擎策略变化都使旧截图失效。"""

    page_config = ProjectAppPageConfig()
    common = dict(page_config=page_config, theme_key="lightblue", theme_config={})
    no_models = PageScreenshotFingerprintService.build_hash(**common)

    first = PageScreenshotFingerprintService.build_hash(**common, model3d_tokens=["product:" + "a" * 64])
    assert first != no_models

    # 资源替换（同名校验值不变、文件哈希变化）必须生成新指纹。
    replaced = PageScreenshotFingerprintService.build_hash(**common, model3d_tokens=["product:" + "b" * 64])
    assert replaced != first

    # 引擎策略身份变化同样必须使旧截图失效。
    monkeypatch.setattr(
        fingerprint_module,
        "load_runtime_kit_manifest",
        lambda: {"model3d_engine": {"engineVersion": "next-engine-version"}},
    )
    changed_engine = PageScreenshotFingerprintService.build_hash(**common, model3d_tokens=["product:" + "a" * 64])
    assert changed_engine != first
