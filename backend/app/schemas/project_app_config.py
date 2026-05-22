"""文件功能：定义项目级 app 配置结构，并提供 YAML 解析、生成与页面展示规格解析能力。"""

from __future__ import annotations

from typing import Literal, TypeAlias

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.exceptions import AppException

DEFAULT_PAGE_WIDTH = 1920
DEFAULT_PAGE_HEIGHT = 1080
DEFAULT_PROJECT_BASE_FONT_SIZE = "20px"
DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN = """## 演示页排版尺度

- 本项目是固定 16:9 演示页/PPT 画布，不是普通网页桌面页。
- 页面应按投屏和远距离阅读设计，避免用网页信息流方式堆内容。
- 主标题优先使用 text-5xl 到 text-7xl。
- 章节标题、模块标题优先使用 text-3xl 到 text-5xl。
- 主体阅读文本优先使用 text-xl 到 text-3xl，不使用 text-sm、text-base 承载主要内容。
- text-xs、text-sm、text-base 只用于页脚、标签、角标、图例、注释或少量辅助信息。
- 单页只表达一个核心结论；内容过多时优先拆页，而不是缩小字号。
- 表格和指标区块应减少列数和行数，优先突出关键数字与结论。"""
DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH = 2
MAX_PAGE_DIMENSION = 8192
DEFAULT_PROJECT_ICON = "slider"
DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON = True
ProjectMenuMode: TypeAlias = Literal["text", "preview", "bottom-preview"]
DEFAULT_PROJECT_MENU_MODE: ProjectMenuMode = "preview"


def normalize_project_base_font_size(value: object) -> object:
    """归一化项目基础字号，只接受 1-200 的整数像素值。"""

    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        raise ValueError("base_font_size 不能为空。")
    if normalized.endswith("px"):
        normalized = normalized[:-2].strip()
    if not normalized.isdigit():
        raise ValueError("base_font_size 仅支持正整数像素值，例如 20px。")
    numeric_value = int(normalized)
    if numeric_value < 1 or numeric_value > 200:
        raise ValueError("base_font_size 必须在 1-200px 之间。")
    return f"{numeric_value}px"


class ProjectAppPageConfig(BaseModel):
    """页面画布与显示规格配置，统一约束运行时预览、截图视口与页面默认视觉规格。"""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=DEFAULT_PAGE_WIDTH, gt=0, le=MAX_PAGE_DIMENSION)
    height: int = Field(default=DEFAULT_PAGE_HEIGHT, gt=0, le=MAX_PAGE_DIMENSION)
    baseFontSize: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32)
    iconDefaultStrokeWidth: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64)

    @field_validator("baseFontSize", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)


class ProjectAppFeaturesConfig(BaseModel):
    """项目级应用功能开关。"""

    model_config = ConfigDict(extra="ignore")

    showPdfExportButton: bool | None = None
    menuMode: ProjectMenuMode | None = None


class ProjectAppSettings(BaseModel):
    """app.config.yaml 中的 app 节点。"""

    model_config = ConfigDict(extra="ignore")

    icon: str = DEFAULT_PROJECT_ICON
    title: str = ""
    description: str = ""
    features: ProjectAppFeaturesConfig = Field(default_factory=ProjectAppFeaturesConfig)
    page: ProjectAppPageConfig = Field(default_factory=ProjectAppPageConfig)


class ProjectAppConfigDocument(BaseModel):
    """项目级 app.config.yaml 文档结构。"""

    model_config = ConfigDict(extra="ignore")

    app: ProjectAppSettings = Field(default_factory=ProjectAppSettings)


def parse_project_app_config_document(yaml_text: str) -> ProjectAppConfigDocument:
    """解析并校验 app.config.yaml 文本。"""

    try:
        parsed_value = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise AppException(
            status_code=400,
            code="PROJECT_CONFIG_INVALID_YAML",
            detail=f"app.config.yaml YAML 语法错误：{exc}",
        ) from exc

    try:
        return ProjectAppConfigDocument.model_validate(parsed_value)
    except ValidationError as exc:
        raise AppException(
            status_code=400,
            code="PROJECT_CONFIG_INVALID_YAML",
            detail=f"app.config.yaml 配置结构不合法：{exc}",
        ) from exc


def build_project_app_config_document(
    *,
    title: str,
    description: str | None,
    icon: str | None,
    page_width: int,
    page_height: int,
    base_font_size: str = DEFAULT_PROJECT_BASE_FONT_SIZE,
    icon_default_stroke_width: int = DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    show_pdf_export_button: bool = DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    menu_mode: ProjectMenuMode = DEFAULT_PROJECT_MENU_MODE,
) -> ProjectAppConfigDocument:
    """基于项目结构化字段构造 Runtime 使用的 app 配置文档。"""

    return ProjectAppConfigDocument(
        app=ProjectAppSettings(
            icon=str(icon or "").strip() or DEFAULT_PROJECT_ICON,
            title=str(title or "").strip(),
            description=str(description or "").strip(),
            page=ProjectAppPageConfig(
                width=page_width,
                height=page_height,
                baseFontSize=base_font_size,
                iconDefaultStrokeWidth=icon_default_stroke_width,
            ),
            features=ProjectAppFeaturesConfig(
                showPdfExportButton=show_pdf_export_button,
                menuMode=menu_mode,
            ),
        )
    )


def dump_project_app_config_document_yaml(document: ProjectAppConfigDocument) -> str:
    """将项目 app 配置文档序列化为 Runtime 可消费的 YAML 文本。"""

    return yaml.safe_dump(
        document.model_dump(mode="python", exclude_none=True),
        allow_unicode=True,
        sort_keys=False,
    )


def resolve_project_page_config(yaml_text: str | None) -> ProjectAppPageConfig:
    """从 app.config.yaml 中解析页面尺寸；为空时回退到默认画布。"""

    if not str(yaml_text or "").strip():
        return ProjectAppPageConfig()
    return parse_project_app_config_document(str(yaml_text)).app.page
