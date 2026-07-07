"""文件功能：定义项目模板包导入导出、元数据、预检和导入结果的接口协议。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PageFileType
from app.schemas.common import SchemaBase
from app.schemas.component import (
    ComponentShareExportAssetSummary,
    ComponentShareExportComponentSummary,
    ComponentSharePackageAssetSummary,
    ComponentSharePackageComponentSummary,
    ComponentSharePackageFontSummary,
)
from app.schemas.project import ProjectBuildExtraAssetsConfig, ProjectMenuMode
from app.schemas.workspace_style import WorkspaceStylePackageThemeSummary


PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION = 1
PROJECT_TEMPLATE_PACKAGE_TYPE = "web-presentation-project-template"


class ProjectTemplateMetadataPayload(BaseModel):
    """模板展示元数据，只允许覆盖当前项目实际存在或可派生的展示字段。"""

    model_config = ConfigDict(extra="forbid")

    slug: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)


class ProjectTemplateExportRequest(BaseModel):
    """导出项目模板包的请求。"""

    model_config = ConfigDict(extra="forbid")

    metadata: ProjectTemplateMetadataPayload = Field(default_factory=ProjectTemplateMetadataPayload)
    cover_page_id: int | None = Field(default=None, ge=1)
    manual_asset_names: list[str] = Field(default_factory=list)
    refresh_screenshots: bool = True


class ProjectTemplatePackageProjectSummary(SchemaBase):
    """模板包中的项目摘要。"""

    source_project_code: str
    name: str
    description: str | None = None
    page_width: int
    page_height: int
    base_font_size: str
    icon_default_stroke_width: int
    show_pdf_export_button: bool
    menu_mode: ProjectMenuMode
    theme_key: str | None = None
    style_spec_markdown: str = ""


class ProjectTemplatePackagePageSummary(SchemaBase):
    """模板包中的页面摘要。"""

    source_page_code: str
    title: str
    summary: str | None = None
    file_type: PageFileType
    action: Literal["create"] = "create"


class ProjectTemplateScreenshotItem(SchemaBase):
    """模板截图摘要。"""

    path: str
    width: int
    height: int
    source_page_code: str | None = None
    title: str | None = None
    order: int | None = None


class ProjectTemplateScreenshotSummary(SchemaBase):
    """模板包截图摘要，包含封面和页面截图数量。"""

    cover: ProjectTemplateScreenshotItem | None = None
    pages: list[ProjectTemplateScreenshotItem] = Field(default_factory=list)


class ProjectTemplateExportValidationResult(SchemaBase):
    """项目模板包导出预检结果。"""

    can_export: bool = True
    project: ProjectTemplatePackageProjectSummary
    pages: list[ProjectTemplatePackagePageSummary] = Field(default_factory=list)
    components: list[ComponentShareExportComponentSummary] = Field(default_factory=list)
    automatic_assets: list[ComponentShareExportAssetSummary] = Field(default_factory=list)
    manual_assets: list[ComponentShareExportAssetSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    fonts: list[ComponentSharePackageFontSummary] = Field(default_factory=list)
    screenshots: ProjectTemplateScreenshotSummary = Field(default_factory=ProjectTemplateScreenshotSummary)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    missing_static_asset_names: list[str] = Field(default_factory=list)
    missing_manual_asset_names: list[str] = Field(default_factory=list)
    dynamic_resource_modules: list[str] = Field(default_factory=list)


class ProjectTemplateImportValidationResult(SchemaBase):
    """项目模板包导入预检结果。"""

    valid: bool
    schema_version: int | None = None
    runtime_kit_manifest_version: str | None = None
    template: dict[str, object] = Field(default_factory=dict)
    project: ProjectTemplatePackageProjectSummary | None = None
    pages: list[ProjectTemplatePackagePageSummary] = Field(default_factory=list)
    components: list[ComponentSharePackageComponentSummary] = Field(default_factory=list)
    assets: list[ComponentSharePackageAssetSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    fonts: list[ComponentSharePackageFontSummary] = Field(default_factory=list)
    screenshots: ProjectTemplateScreenshotSummary = Field(default_factory=ProjectTemplateScreenshotSummary)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProjectTemplateImportResult(SchemaBase):
    """项目模板包正式导入结果。"""

    project_id: int
    project_code: str
    project_name: str
    page_ids: list[int] = Field(default_factory=list)
    pages: list[ProjectTemplatePackagePageSummary] = Field(default_factory=list)
    components: list[ComponentSharePackageComponentSummary] = Field(default_factory=list)
    assets: list[ComponentSharePackageAssetSummary] = Field(default_factory=list)
    themes: list[WorkspaceStylePackageThemeSummary] = Field(default_factory=list)
    fonts: list[ComponentSharePackageFontSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProjectTemplatePackageManifest(SchemaBase):
    """模板包 manifest 的稳定字段集合。"""

    package_type: str
    schema_version: int
    exported_at: datetime
    runtime_kit_manifest_version: str | None = None
    template_path: str = "metadata/template.json"
    screenshots_path: str = "metadata/screenshots.json"
    project_path: str = "project/project.json"
    routes_path: str = "project/routes.json"
    page_count: int
    component_count: int
    asset_count: int
    theme_count: int
    font_count: int
    build_extra_assets_json: ProjectBuildExtraAssetsConfig = Field(default_factory=ProjectBuildExtraAssetsConfig)
