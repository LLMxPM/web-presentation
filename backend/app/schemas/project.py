"""文件功能：定义项目实体的请求与响应模型。"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import RecordStatus
from app.schemas.common import SchemaBase
from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
    ProjectMenuMode,
    normalize_project_base_font_size,
)


class ProjectCreateRequest(BaseModel):
    """创建项目入参，code 由后端自动生成，必须指定所属工作空间。"""

    model_config = ConfigDict(extra="forbid")

    workspace_id: int
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus = RecordStatus.ACTIVE
    page_width: int = Field(default=DEFAULT_PAGE_WIDTH, ge=1, le=8192)
    page_height: int = Field(default=DEFAULT_PAGE_HEIGHT, ge=1, le=8192)
    base_font_size: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32)
    icon_default_stroke_width: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64)
    show_pdf_export_button: bool = True
    menu_mode: ProjectMenuMode = "preview"
    theme_key: str | None = Field(default=None, min_length=1, max_length=64)
    theme_config_yaml: str | None = None
    style_spec_markdown: str = DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN

    @field_validator("base_font_size", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)

    @field_validator("style_spec_markdown", mode="before")
    @classmethod
    def normalize_style_spec_markdown(cls, value: object) -> str:
        """统一样式规范换行，保持 Markdown 纯文本稳定。"""

        return normalize_text_to_lf(None if value is None else str(value))


class ProjectUpdateRequest(BaseModel):
    """更新项目入参，允许修改工作空间和基本元数据（code 不可修改）。"""

    model_config = ConfigDict(extra="forbid")

    workspace_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus | None = None
    page_width: int | None = Field(default=None, ge=1, le=8192)
    page_height: int | None = Field(default=None, ge=1, le=8192)
    base_font_size: str | None = Field(default=None, min_length=1, max_length=32)
    icon_default_stroke_width: int | None = Field(default=None, ge=1, le=64)
    show_pdf_export_button: bool | None = None
    menu_mode: ProjectMenuMode | None = None
    theme_key: str | None = Field(default=None, min_length=1, max_length=64)
    theme_config_yaml: str | None = None
    style_spec_markdown: str | None = None

    @field_validator("base_font_size", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)

    @field_validator("style_spec_markdown", mode="before")
    @classmethod
    def normalize_style_spec_markdown(cls, value: object) -> str | None:
        """统一样式规范换行，保留 None 供更新请求表示未传或清空。"""

        if value is None:
            return None
        return normalize_text_to_lf(str(value))


class ProjectItem(SchemaBase):
    """项目响应模型，同时返回所属工作空间信息。"""

    id: int
    workspace_id: int
    workspace_name: str
    code: str
    name: str
    description: str | None
    is_system_managed: bool = False
    status: RecordStatus
    archived_at: datetime | None
    page_width: int
    page_height: int
    base_font_size: str
    icon_default_stroke_width: int
    show_pdf_export_button: bool
    menu_mode: ProjectMenuMode
    theme_key: str | None
    theme_config_yaml: str
    style_spec_markdown: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None
