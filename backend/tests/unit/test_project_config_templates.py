"""文件功能：验证 Backend 默认项目配置模板的读取位置、内容完整性与 YAML 可解析性。"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_MENU_MODE,
    DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    parse_project_app_config_document,
)
from app.services.project_config_service import (
    CONFIG_FILE_MAP,
    PROJECT_CONFIG_TEMPLATE_ROOT,
    load_default_project_config_templates,
)


def test_default_project_config_templates_should_be_backend_owned() -> None:
    """默认项目配置模板应由 Backend 自己携带，避免生产镜像依赖 Runtime 目录。"""

    backend_root = Path(__file__).resolve().parents[2]

    assert PROJECT_CONFIG_TEMPLATE_ROOT == backend_root / "app" / "config_templates"


def test_default_project_config_templates_should_be_loadable_yaml() -> None:
    """所有默认项目配置模板都应存在、可读取且是 YAML 对象。"""

    load_default_project_config_templates.cache_clear()
    templates = load_default_project_config_templates()

    assert set(templates) == set(CONFIG_FILE_MAP)
    for config_name, file_name in CONFIG_FILE_MAP.items():
        template_path = PROJECT_CONFIG_TEMPLATE_ROOT / file_name
        parsed_value = yaml.safe_load(templates[config_name])

        assert template_path.is_file()
        assert templates[config_name] == template_path.read_text(encoding="utf-8")
        assert isinstance(parsed_value, dict)


def test_default_app_template_should_keep_required_runtime_defaults() -> None:
    """app 模板只保留 Runtime 需要的页面规格和功能开关默认值。"""

    load_default_project_config_templates.cache_clear()
    document = parse_project_app_config_document(load_default_project_config_templates()["app"])

    assert document.app.page.width == DEFAULT_PAGE_WIDTH
    assert document.app.page.height == DEFAULT_PAGE_HEIGHT
    assert document.app.page.baseFontSize == DEFAULT_PROJECT_BASE_FONT_SIZE
    assert document.app.page.iconDefaultStrokeWidth == DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH
    assert document.app.features.showPdfExportButton is DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON
    assert document.app.features.menuMode == DEFAULT_PROJECT_MENU_MODE


def test_default_theme_template_should_keep_minimal_runtime_theme_shape() -> None:
    """themes 模板只保留一个默认主题及 Runtime 样式变量需要的最小字段。"""

    load_default_project_config_templates.cache_clear()
    themes_config = yaml.safe_load(load_default_project_config_templates()["themes"])
    default_theme_key = themes_config["default"]["theme"]
    theme = themes_config["themes"][default_theme_key]

    assert default_theme_key == "lightblue"
    assert set(theme["palette"]) == {"text", "background", "border", "link", "accent"}
    assert set(theme["palette"]["text"]) == {"primary", "secondary", "invert"}
    assert set(theme["palette"]["background"]) == {"default", "invert"}
    assert set(theme["palette"]["border"]) == {"default", "subtle"}
    assert set(theme["palette"]["link"]) == {"default", "hover", "visited"}
    assert len(theme["palette"]["accent"]) == 6
    assert theme["typography"] == {
        "headingfont": "system-ui",
        "bodyfont": "system-ui",
        "codefont": "monospace",
    }


def test_default_icon_template_should_not_embed_runtime_fixture_icons() -> None:
    """icons 模板只提供空配置壳，真实图标由资源库按预览依赖动态生成。"""

    load_default_project_config_templates.cache_clear()
    icon_config = yaml.safe_load(load_default_project_config_templates()["icons"])

    assert icon_config == {"static_icons": []}
