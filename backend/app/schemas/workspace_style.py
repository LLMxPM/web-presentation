"""文件功能：定义工作空间样式库的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import SchemaBase
from app.schemas.presentation_style import StyleConfiguration, StyleConfigurationPatch
from app.schemas.project_app_config import ProjectMenuMode


def _normalize_style_key(value: object) -> object:
    """归一化样式 key，兼容用户输入的大写与首尾空白。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower()
    return value


class WorkspaceStyleBaseRequest(BaseModel):
    """工作空间样式创建请求的标识与完整配置。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    configuration: StyleConfiguration = Field(default_factory=StyleConfiguration)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将样式 key 归一化为小写。"""

        return _normalize_style_key(value)

class WorkspaceStyleCreateRequest(WorkspaceStyleBaseRequest):
    """创建样式请求。"""


class WorkspaceStyleUpdateRequest(BaseModel):
    """更新样式请求，key 创建后不可修改。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    configuration: StyleConfigurationPatch | None = None

    @model_validator(mode="after")
    def require_update(self) -> "WorkspaceStyleUpdateRequest":
        """拒绝没有元数据或配置字段的空更新。"""

        if not self.model_fields_set:
            raise ValueError("样式更新至少需要提供一个字段。")
        return self


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
    manual_asset_names: list[str] = Field(default_factory=list)


class WorkspaceStyleExportAssetSummary(SchemaBase):
    """样式离线包导出预检中的资源摘要。"""

    name: str
    original_name: str
    asset_type: str
    file_hash: str
    source: str = "automatic"


class WorkspaceStyleExportValidationResult(SchemaBase):
    """样式离线包导出预检结果。"""

    can_export: bool = True
    automatic_assets: list[WorkspaceStyleExportAssetSummary] = Field(default_factory=list)
    manual_assets: list[WorkspaceStyleExportAssetSummary] = Field(default_factory=list)
    fonts: list[WorkspaceStylePackageFontSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_static_asset_names: list[str] = Field(default_factory=list)
    missing_manual_asset_names: list[str] = Field(default_factory=list)
    dynamic_resource_components: list[str] = Field(default_factory=list)


class WorkspaceStylePackageStyleSummary(SchemaBase):
    """样式离线包中的样式摘要。"""

    key: str
    name: str
    theme_key: str | None = None
    page_width: int
    page_height: int
    base_font_size: str
    icon_default_stroke_width: int
    show_pdf_export_button: bool
    menu_mode: ProjectMenuMode
    style_spec_markdown: str = ""
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


class WorkspaceStylePackageComponentSummary(SchemaBase):
    """样式离线包中的组件摘要。"""

    source_component_code: str
    source_version_no: int
    name: str
    import_name: str
    component_type: str
    dependencies: list[str] = Field(default_factory=list)
    component_fingerprint: str | None = None
    matched_component_id: int | None = None
    matched_component_code: str | None = None
    action: str = "create"
    match_reason: str | None = None


class WorkspaceStyleImportValidationResult(SchemaBase):
    """样式离线包导入预检结果。"""

    valid: bool
    schema_version: int | None = None
    styles: list[WorkspaceStylePackageStyleSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    assets: list[WorkspaceStylePackageAssetSummary] = Field(default_factory=list)
    fonts: list[WorkspaceStylePackageFontSummary] = Field(default_factory=list)
    components: list[WorkspaceStylePackageComponentSummary] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkspaceStyleImportResult(SchemaBase):
    """样式离线包正式导入结果。"""

    styles: list[WorkspaceStylePackageStyleSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    assets: list[WorkspaceStylePackageAssetSummary] = Field(default_factory=list)
    fonts: list[WorkspaceStylePackageFontSummary] = Field(default_factory=list)
    components: list[WorkspaceStylePackageComponentSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
