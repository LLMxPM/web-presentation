"""文件功能：定义工作空间样式库的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_normalizer import normalize_text_to_lf
from app.schemas.common import SchemaBase
from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_MENU_MODE,
    DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
    ProjectMenuMode,
    normalize_project_base_font_size,
)


def _normalize_style_key(value: object) -> object:
    """归一化样式 key，兼容用户输入的大写与首尾空白。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _normalize_optional_theme_key(value: object) -> object:
    """归一化可选主题 key，空白字符串视为不覆盖项目主题。"""

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class WorkspaceStyleBaseRequest(BaseModel):
    """工作空间样式写入请求的公共字段。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    page_width: int = Field(default=DEFAULT_PAGE_WIDTH, ge=1, le=8192)
    page_height: int = Field(default=DEFAULT_PAGE_HEIGHT, ge=1, le=8192)
    base_font_size: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32)
    icon_default_stroke_width: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64)
    show_pdf_export_button: bool = DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON
    menu_mode: ProjectMenuMode = DEFAULT_PROJECT_MENU_MODE
    theme_key: str | None = Field(default=None, min_length=1, max_length=64)
    style_spec_markdown: str = DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将样式 key 归一化为小写。"""

        return _normalize_style_key(value)

    @field_validator("base_font_size", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)

    @field_validator("theme_key", mode="before")
    @classmethod
    def normalize_theme_key(cls, value: object) -> object:
        """将空白主题 key 视为不指定主题。"""

        return _normalize_optional_theme_key(value)

    @field_validator("style_spec_markdown", mode="before")
    @classmethod
    def normalize_style_spec_markdown(cls, value: object) -> str:
        """统一样式规范换行，保持纯文本 Markdown 可稳定比对。"""

        return normalize_text_to_lf(None if value is None else str(value))


class WorkspaceStyleCreateRequest(WorkspaceStyleBaseRequest):
    """创建样式请求。"""


class WorkspaceStyleUpdateRequest(BaseModel):
    """更新样式请求，所有字段均可选。"""

    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    page_width: int | None = Field(default=None, ge=1, le=8192)
    page_height: int | None = Field(default=None, ge=1, le=8192)
    base_font_size: str | None = Field(default=None, min_length=1, max_length=32)
    icon_default_stroke_width: int | None = Field(default=None, ge=1, le=64)
    show_pdf_export_button: bool | None = None
    menu_mode: ProjectMenuMode | None = None
    theme_key: str | None = Field(default=None, min_length=1, max_length=64)
    style_spec_markdown: str | None = None

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将样式 key 归一化为小写。"""

        return _normalize_style_key(value)

    @field_validator("base_font_size", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)

    @field_validator("theme_key", mode="before")
    @classmethod
    def normalize_theme_key(cls, value: object) -> object:
        """将空白主题 key 视为不指定主题。"""

        return _normalize_optional_theme_key(value)

    @field_validator("style_spec_markdown", mode="before")
    @classmethod
    def normalize_style_spec_markdown(cls, value: object) -> str | None:
        """统一样式规范换行，保留 None 表示字段未传或显式清空。"""

        if value is None:
            return None
        return normalize_text_to_lf(str(value))


class WorkspaceStyleCopyRequest(BaseModel):
    """复制样式请求。"""

    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将样式 key 归一化为小写。"""

        return _normalize_style_key(value)


class WorkspaceStyleExportPackageRequest(BaseModel):
    """导出样式离线包请求。"""

    style_ids: list[int] = Field(min_length=1, max_length=100)


class WorkspaceStylePackageStyleSummary(SchemaBase):
    """样式离线包中的样式摘要。"""

    key: str
    name: str
    theme_key: str | None = None
    action: str = "create"


class WorkspaceStylePackageThemeSummary(SchemaBase):
    """样式离线包中的主题摘要。"""

    key: str
    name: str
    action: str = "create"


class WorkspaceStylePackageAssetSummary(SchemaBase):
    """样式离线包中的资源摘要。"""

    name: str
    original_name: str
    asset_type: str
    file_hash: str
    action: str = "create"


class WorkspaceStylePackageFontSummary(SchemaBase):
    """样式离线包中的字体配置摘要。"""

    asset_name: str
    font_family: str
    font_format: str
    font_weight: str
    font_style: str
    font_display: str
    status: str
    action: str = "create"


class WorkspaceStyleImportValidationResult(SchemaBase):
    """样式离线包导入预检结果。"""

    valid: bool
    schema_version: int | None = None
    styles: list[WorkspaceStylePackageStyleSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    assets: list[WorkspaceStylePackageAssetSummary] = Field(default_factory=list)
    fonts: list[WorkspaceStylePackageFontSummary] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class WorkspaceStyleImportResult(SchemaBase):
    """样式离线包正式导入结果。"""

    styles: list[WorkspaceStylePackageStyleSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    assets: list[WorkspaceStylePackageAssetSummary] = Field(default_factory=list)
    fonts: list[WorkspaceStylePackageFontSummary] = Field(default_factory=list)


class WorkspaceStyleItem(SchemaBase):
    """工作空间样式响应模型。"""

    id: int
    workspace_id: int
    key: str
    name: str
    description: str | None
    page_width: int
    page_height: int
    base_font_size: str
    icon_default_stroke_width: int
    show_pdf_export_button: bool
    menu_mode: ProjectMenuMode
    theme_key: str | None
    style_spec_markdown: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None
