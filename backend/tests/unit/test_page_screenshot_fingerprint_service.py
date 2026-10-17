"""文件功能：验证页面截图指纹会随平台字体版本与引用资源身份变化而失效。"""

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


def test_screenshot_fingerprint_should_include_resource_identity(monkeypatch) -> None:
    """引用资源实时身份入截图指纹；引擎身份只影响三维引用页面。"""

    page_config = ProjectAppPageConfig()
    common = dict(page_config=page_config, theme_key="lightblue", theme_config={})
    no_resources = PageScreenshotFingerprintService.build_hash(**common)

    # 图片等非三维资源替换（同名、文件哈希变化）必须生成新指纹。
    image_first = PageScreenshotFingerprintService.build_hash(**common, resource_tokens=["asset:hero:" + "a" * 64])
    assert image_first != no_resources
    replaced_image = PageScreenshotFingerprintService.build_hash(**common, resource_tokens=["asset:hero:" + "b" * 64])
    assert replaced_image != image_first

    # 三维资源替换同样必须生成新指纹。
    model_first = PageScreenshotFingerprintService.build_hash(
        **common, resource_tokens=["asset:product:" + "a" * 64], has_model3d=True
    )
    assert model_first != no_resources
    replaced_model = PageScreenshotFingerprintService.build_hash(
        **common, resource_tokens=["asset:product:" + "b" * 64], has_model3d=True
    )
    assert replaced_model != model_first

    # 引擎策略身份变化使三维页面旧截图失效，但不影响仅引用非三维资源的页面。
    monkeypatch.setattr(
        fingerprint_module,
        "load_runtime_kit_manifest",
        lambda: {"model3d_engine": {"engineVersion": "next-engine-version"}},
    )
    changed_engine = PageScreenshotFingerprintService.build_hash(
        **common, resource_tokens=["asset:product:" + "a" * 64], has_model3d=True
    )
    assert changed_engine != model_first
    assert (
        PageScreenshotFingerprintService.build_hash(**common, resource_tokens=["asset:hero:" + "a" * 64])
        == image_first
    )
