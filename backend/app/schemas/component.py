"""文件功能：定义工作空间组件的请求与响应模型，以及版本、依赖索引与分享包响应。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.schemas.common import ListQuery, SchemaBase
from app.schemas.component_preview_options import ComponentPreviewOptions

COMPONENT_IMPORT_NAME_PATTERN = r"^[A-Z][A-Za-z0-9]{0,63}$"


def normalize_component_import_name(value: str) -> str:
    """归一化组件源码引用名，去除用户输入首尾空白。"""

    return str(value or "").strip()


class WorkspaceComponentCreateRequest(BaseModel):
    """创建工作空间组件入参，code 由后端自动生成。"""

    workspace_id: int
    content: str = Field(min_length=1)
    file_type: PageFileType = PageFileType.VUE
    name: str = Field(min_length=1, max_length=128)
    import_name: str = Field(min_length=1, max_length=64, pattern=COMPONENT_IMPORT_NAME_PATTERN)
    component_type: WorkspaceComponentType = WorkspaceComponentType.CONTENT_BLOCK
    summary: str | None = Field(default=None, max_length=2000)
    preview_schema: str | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    change_note: str | None = Field(default=None, max_length=255)

    @field_validator("import_name", mode="before")
    @classmethod
    def normalize_import_name(cls, value: str) -> str:
        """在格式校验前清理引用名空白。"""

        return normalize_component_import_name(value)


class WorkspaceComponentUpdateRequest(BaseModel):
    """更新工作空间组件入参，支持元数据和源码局部更新。"""

    workspace_id: int | None = None
    content: str | None = Field(default=None, min_length=1)
    file_type: PageFileType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    import_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=COMPONENT_IMPORT_NAME_PATTERN,
    )
    component_type: WorkspaceComponentType | None = None
    summary: str | None = Field(default=None, max_length=2000)
    preview_schema: str | None = None
    status: RecordStatus | None = None
    change_note: str | None = Field(default=None, max_length=255)

    @field_validator("import_name", mode="before")
    @classmethod
    def normalize_import_name(cls, value: str | None) -> str | None:
        """在格式校验前清理引用名空白。"""

        if value is None:
            return None
        return normalize_component_import_name(value)

    @model_validator(mode="after")
    def reject_null_import_name(self) -> "WorkspaceComponentUpdateRequest":
        """引用名允许省略，但不允许显式传空值清除。"""

        if "import_name" in self.model_fields_set and self.import_name is None:
            raise ValueError("import_name 不能为 null。")
        return self


class WorkspaceComponentSourcePreviewRequest(BaseModel):
    """基于未保存源码生成组件草稿预览的入参。"""

    workspace_id: int
    component_id: int | None = None
    component_name: str | None = Field(default=None, max_length=128)
    content: str = Field(min_length=1)
    preview_schema: str | None = None
    preview_options: ComponentPreviewOptions | None = None
    file_type: PageFileType = PageFileType.VUE


class WorkspaceComponentListQuery(ListQuery):
    """组件列表查询参数。"""

    workspace_id: int | None = None
    component_type: WorkspaceComponentType | None = None


class WorkspaceComponentDependencyItem(SchemaBase):
    """组件或页面当前版本的源码依赖项。"""

    dependency_kind: str
    component_code: str | None = None
    component_version_no: int | None = None
    runtime_module_path: str | None = None


class WorkspaceComponentItem(SchemaBase):
    """工作空间组件响应模型，当前源码字段表示可编辑草稿。"""

    id: int
    workspace_id: int
    workspace_name: str | None = None
    code: str
    content: str
    preview_schema: str | None
    current_version_no: int
    draft_base_version_no: int
    has_unpublished_changes: bool
    published_at: datetime | None
    file_type: PageFileType
    name: str
    import_name: str
    component_type: WorkspaceComponentType
    summary: str | None
    status: RecordStatus
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


class WorkspaceComponentVersionListItem(SchemaBase):
    """工作空间组件发布版本列表项。"""

    id: int
    component_id: int
    version_no: int
    version_label: str
    release_name: str | None
    file_type: PageFileType
    is_current: bool
    content_size: int
    change_note: str | None
    created_at: datetime
    created_by: int | None


class WorkspaceComponentVersionContent(SchemaBase):
    """工作空间组件发布版本完整内容。"""

    component_id: int
    version_no: int
    version_label: str
    release_name: str | None
    file_type: PageFileType
    is_current: bool
    content: str
    preview_schema: str | None
    change_note: str | None
    created_at: datetime
    created_by: int | None


class WorkspaceComponentCurrentDependencies(SchemaBase):
    """工作空间组件当前版本依赖索引响应。"""

    component_id: int
    current_version_no: int
    component_version_id: int | None
    dependencies: list[WorkspaceComponentDependencyItem]


class WorkspaceComponentPublishRequest(BaseModel):
    """组件草稿发布入参，发布后生成可被外部引用的不可变版本。"""

    release_name: str | None = Field(default=None, max_length=128)
    change_note: str | None = Field(default=None, max_length=255)


class WorkspaceComponentRestoreDraftRequest(BaseModel):
    """将指定发布版本恢复为草稿时的入参。"""

    change_note: str | None = Field(default=None, max_length=255)


class WorkspaceComponentExportPackageRequest(BaseModel):
    """导出工作空间组件离线分享包的入参。"""

    workspace_id: int
    component_ids: list[int] = Field(min_length=1)


class ComponentSharePackageComponentSummary(SchemaBase):
    """分享包内组件摘要，用于预检和导入结果展示。"""

    source_component_code: str
    source_version_no: int
    name: str
    import_name: str
    component_type: str
    dependencies: list[str] = Field(default_factory=list)


class ComponentSharePackageAssetSummary(SchemaBase):
    """分享包内资源摘要，用于展示导入动作。"""

    name: str
    original_name: str
    asset_type: str
    file_hash: str
    action: str = "create"


class ComponentSharePackageFontSummary(SchemaBase):
    """分享包内字体配置摘要，用于展示导入动作。"""

    asset_name: str
    font_family: str
    font_format: str
    font_weight: str
    font_style: str
    font_display: str
    status: str
    action: str = "create"


class ComponentShareImportValidationResult(SchemaBase):
    """组件分享包导入预检结果。"""

    valid: bool
    schema_version: int | None = None
    runtime_kit_manifest_version: str | None = None
    components: list[ComponentSharePackageComponentSummary] = Field(default_factory=list)
    assets: list[ComponentSharePackageAssetSummary] = Field(default_factory=list)
    fonts: list[ComponentSharePackageFontSummary] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ComponentShareImportResult(SchemaBase):
    """组件分享包正式导入结果。"""

    imported_components: list[WorkspaceComponentItem] = Field(default_factory=list)
    assets: list[ComponentSharePackageAssetSummary] = Field(default_factory=list)
    fonts: list[ComponentSharePackageFontSummary] = Field(default_factory=list)
