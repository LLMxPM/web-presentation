"""文件功能：定义静态资源序列化协议模型，覆盖资源元数据、内容编辑与归档交互。"""

from datetime import datetime

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.models.enums import AssetRole, AssetType, RecordStatus
from app.services.asset_render_metadata_service import AssetRenderMetadataService


FOUNDATION_ASSET_TYPES = {AssetType.ICON, AssetType.FONT}


def resolve_asset_role(asset_type: AssetType | str) -> AssetRole:
    """根据资源类型推导平台职责分组。"""

    resolved_type = asset_type if isinstance(asset_type, AssetType) else AssetType(str(asset_type))
    return AssetRole.FOUNDATION if resolved_type in FOUNDATION_ASSET_TYPES else AssetRole.CONTENT


class AssetFontConfigSummary(BaseModel):
    """资产列表中携带的字体配置摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    asset_name: str
    font_family: str
    font_format: str
    font_weight: str
    font_style: str
    font_display: str
    status: RecordStatus


class AssetIconAnalysisPayload(BaseModel):
    """图标资产分析结果的结构化载荷。"""

    format: Literal["svg", "image", "unknown"] = "unknown"
    render_mode: Literal["inline_svg", "image"] = "image"
    style: Literal["stroke", "fill", "mixed", "complex", "unknown"] = "unknown"
    inline_safe: bool = False
    stroke_width_editable: bool = False
    analysis_status: Literal["analyzed", "unsupported", "error"] = "unsupported"
    reasons: list[str] = Field(default_factory=list)


class AssetAnalysisMetadata(BaseModel):
    """资产机器分析结构化元数据。"""

    schema_version: int = 1
    kind: Literal["icon"] = "icon"
    icon: AssetIconAnalysisPayload


class AssetResponse(BaseModel):
    """公开静态资源返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    file_name: str
    original_name: str
    description: str | None = None
    file_size: int
    file_hash: str
    content_type: str | None = None
    asset_type: AssetType
    asset_role: AssetRole = AssetRole.CONTENT
    render_type: AssetType = AssetType.IMAGE
    tags: list[str] = Field(default_factory=list)
    analysis_metadata: AssetAnalysisMetadata | None = None
    render_metadata: dict | None = None
    approx_aspect_ratio: str | None = None
    approx_aspect_ratio_value: float | None = None
    aspect_ratio_source: str | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    archived_at: datetime | None = None
    archive_reason: str | None = None
    source_asset_id: int | None = None
    history_kind: str | None = None
    content_editable: bool = False
    url: str | None = None
    font_config: AssetFontConfigSummary | None = None
    rename_block_reason: str | None = None
    delete_block_reason: str | None = None
    archive_block_reason: str | None = None
    archive_warning_reasons: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def fill_derived_asset_fields(self) -> "AssetResponse":
        """补齐由 asset_type 派生的角色、渲染类型与近似比例摘要。"""

        self.asset_role = resolve_asset_role(self.asset_type)
        self.render_type = self.asset_type
        ratio_summary = AssetRenderMetadataService.summarize_metadata(self.render_metadata)
        self.approx_aspect_ratio = ratio_summary["approx_aspect_ratio"]
        self.approx_aspect_ratio_value = ratio_summary["approx_aspect_ratio_value"]
        self.aspect_ratio_source = ratio_summary["aspect_ratio_source"]
        self.content_editable = resolve_asset_content_editable(
            self.asset_type,
            self.original_name,
            self.content_type,
        )
        return self


class AssetUpdateRequest(BaseModel):
    """更新静态资源（如改名或修改标签）。"""

    name: Optional[str] = None
    original_name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    approx_aspect_ratio: Optional[str] = None


def resolve_asset_content_editable(
    asset_type: AssetType | str,
    original_name: str | None,
    content_type: str | None = None,
) -> bool:
    """判断资源是否允许作为文本内容被读取和写回。"""

    resolved_type = asset_type if isinstance(asset_type, AssetType) else AssetType(str(asset_type))
    if resolved_type in {AssetType.DRAWIO, AssetType.MERMAID, AssetType.CHART, AssetType.FORMULA}:
        return True
    if resolved_type not in {AssetType.ICON, AssetType.IMAGE}:
        return False
    normalized_name = str(original_name or "").strip().lower()
    normalized_content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    return normalized_name.endswith(".svg") or normalized_content_type == "image/svg+xml"


class AssetContentCreateRequest(BaseModel):
    """通过文本内容创建可编辑资源的请求体。"""

    asset_type: AssetType
    name: str = Field(min_length=1, max_length=255)
    original_name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    approx_aspect_ratio: str | None = None


class AssetContentUpdateRequest(BaseModel):
    """替换可编辑资源内容的请求体。"""

    content: str = Field(min_length=1)
    change_note: str | None = Field(default=None, max_length=255)


class AssetContentResponse(BaseModel):
    """返回可编辑资源的文本内容。"""

    asset: AssetResponse
    content: str


class AssetContentPreviewRequest(BaseModel):
    """预览资源内容改动的请求体。"""

    content: str = Field(min_length=1)


class AssetContentPreviewResponse(BaseModel):
    """资源内容改动预览结果。"""

    asset_id: int
    asset_name: str
    changed: bool
    unified_diff: str


class AssetCopyRequest(BaseModel):
    """复制资源记录的请求体。"""

    name: str | None = Field(default=None, max_length=255)
    original_name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    tags: list[str] | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    archive_reason: str | None = None


class AssetArchiveRequest(BaseModel):
    """归档资源的请求体。"""

    archive_reason: str | None = Field(default=None, max_length=1000)


class AssetRestoreRequest(BaseModel):
    """恢复归档资源的请求体。"""

    restore_reason: str | None = Field(default=None, max_length=1000)


class AssetBatchArchiveRequest(BaseModel):
    """批量归档资源的请求体。"""

    asset_ids: list[int] = Field(min_length=1, max_length=100)
    archive_reason: str | None = Field(default=None, max_length=1000)


class AssetBatchDeleteRequest(BaseModel):
    """批量删除资源的请求体。"""

    asset_ids: list[int] = Field(min_length=1, max_length=100)


class AssetPackageExportRequest(BaseModel):
    """资源离线包导出的请求体。"""

    asset_ids: list[int] = Field(min_length=1, max_length=100)


class AssetBatchOperationFailure(BaseModel):
    """批量资源操作中单个资源失败的明细。"""

    asset_id: int
    code: str
    detail: str


class AssetBatchOperationResponse(BaseModel):
    """批量资源操作结果汇总，保留逐项失败原因。"""

    requested_count: int
    succeeded_count: int
    failed_count: int
    asset_ids: list[int] = Field(default_factory=list)
    failures: list[AssetBatchOperationFailure] = Field(default_factory=list)


class AssetPackageImportFailure(BaseModel):
    """资源离线包导入中单个资源失败的明细。"""

    name: str
    code: str
    detail: str


class AssetPackageImportItem(BaseModel):
    """资源离线包导入后单个资源的处理结果。"""

    name: str
    original_name: str
    asset_type: AssetType
    file_hash: str
    action: Literal["create", "update_metadata", "reuse"]
    asset_id: int | None = None


class AssetPackageImportResult(BaseModel):
    """资源离线包导入汇总结果。"""

    imported_count: int = 0
    updated_count: int = 0
    reused_count: int = 0
    failed_count: int = 0
    assets: list[AssetPackageImportItem] = Field(default_factory=list)
    failures: list[AssetPackageImportFailure] = Field(default_factory=list)


class AssetReferenceSummary(BaseModel):
    """描述资源当前被哪些业务对象引用。"""

    theme_count: int = 0
    font_count: int = 0
    page_count: int = 0
    component_count: int = 0
    component_version_count: int = 0
    references: list[dict[str, object]] = Field(default_factory=list)

    @computed_field
    @property
    def has_references(self) -> bool:
        """判断资源是否存在任意引用。"""

        return any(
            [
                self.theme_count,
                self.font_count,
                self.page_count,
                self.component_count,
                self.component_version_count,
            ]
        )
