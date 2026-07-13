"""文件功能：定义工作空间页面资源库的请求与响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PageFileType, PageVersionStorageType, RecordStatus
from app.schemas.common import ListQuery, SchemaBase
from app.schemas.project_route import ProjectRoutePageBinding


class PageCreateRequest(BaseModel):
    """创建页面资源入参，code 由后端自动生成。"""

    page_content: str = Field(min_length=1)
    file_type: PageFileType = PageFileType.VUE
    title: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=500)
    speaker_notes: str | None = Field(default=None, max_length=10000)
    status: RecordStatus = RecordStatus.ACTIVE
    workspace_id: int | None = None
    project_id: int | None = None


class PageUpdateRequest(BaseModel):
    """更新页面资源入参，支持元数据级别的局部变更（code 不可修改）。"""

    page_content: str | None = Field(default=None, min_length=1)
    file_type: PageFileType | None = None
    change_note: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=500)
    speaker_notes: str | None = Field(default=None, max_length=10000)
    status: RecordStatus | None = None
    workspace_id: int | None = None
    project_id: int | None = None


class PageCopyToProjectRequest(BaseModel):
    """页面复制到目标项目的入参。"""

    model_config = ConfigDict(extra="forbid")

    target_project_id: int = Field(gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=500)
    route_placement: Literal["none", "root", "group"] = "none"
    parent_route_id: int | None = Field(default=None, ge=1)
    route: str | None = Field(default=None, min_length=1, max_length=128)


class PageItem(SchemaBase):
    """页面资源响应模型，返回全局资源库所需字段。"""

    id: int
    code: str
    page_content: str
    current_version_no: int
    file_type: PageFileType
    title: str
    summary: str | None
    speaker_notes: str | None = None
    status: RecordStatus
    workspace_id: int | None
    workspace_name: str | None = None
    project_id: int | None
    project_name: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None
    screenshot_url: str | None = None
    screenshot_version_no: int | None = None
    screenshot_config_hash: str | None = None
    screenshot_viewport_width: int | None = None
    screenshot_viewport_height: int | None = None
    screenshot_is_latest: bool = False
    screenshot_updated_at: datetime | None = None
    is_in_project_route: bool | None = None
    route_bindings: list[ProjectRoutePageBinding] = Field(default_factory=list)


class PageListQuery(ListQuery):
    """资源库额外的过滤参数。"""

    workspace_id: int | None = None
    project_id: int | None = None


class PageVersionListItem(SchemaBase):
    """页面版本列表项，描述一个可供查看或恢复的历史节点。"""

    id: int
    page_id: int
    version_no: int
    version_label: str
    file_type: PageFileType
    storage_type: PageVersionStorageType
    is_important: bool
    is_current: bool
    snapshot_name: str | None
    change_note: str | None
    content_size: int
    created_at: datetime
    created_by: int | None


class PageVersionContent(SchemaBase):
    """单个页面版本的完整内容响应。"""

    page_id: int
    version_no: int
    version_label: str
    file_type: PageFileType
    storage_type: PageVersionStorageType
    is_important: bool
    snapshot_name: str | None
    change_note: str | None
    speaker_notes: str | None = None
    content_mode: Literal["full", "diff"]
    content: str
    resolved_content: str
    created_at: datetime
    created_by: int | None


class PageSnapshotCreateRequest(BaseModel):
    """创建或升级重点快照的入参。"""

    snapshot_name: str | None = Field(default=None, max_length=128)


class PageVersionRestoreRequest(BaseModel):
    """恢复历史版本时允许附带的备注信息。"""

    change_note: str | None = Field(default=None, max_length=255)


class PageScreenshotRequest(BaseModel):
    """页面截图请求，允许显式传入本次截图视口。"""

    viewport_width: int | None = Field(default=None, ge=1, le=8192)
    viewport_height: int | None = Field(default=None, ge=1, le=8192)


class PageScreenshotBatchRefreshRequest(BaseModel):
    """批量刷新页面截图请求。"""

    project_id: int = Field(gt=0)


class PageScreenshotBatchDownloadRequest(BaseModel):
    """批量下载页面截图请求。"""

    page_ids: list[int] = Field(min_length=1, max_length=100)


class PageScreenshotBatchFailure(BaseModel):
    """批量刷新截图中单页失败明细。"""

    page_id: int
    code: str
    detail: str


class PageScreenshotBatchRefreshResponse(BaseModel):
    """批量刷新截图结果汇总。"""

    requested_count: int
    succeeded_count: int
    failed_count: int
    page_ids: list[int] = Field(default_factory=list)
    failures: list[PageScreenshotBatchFailure] = Field(default_factory=list)


PageScreenshotJobStatus = Literal["pending", "running", "succeeded", "failed", "skipped", "cancelled"]
PageScreenshotJobGroupStatus = Literal["pending", "running", "succeeded", "failed", "partial", "cancelled"]


class PageScreenshotJobRequest(BaseModel):
    """创建单页截图任务请求，允许显式传入本次截图视口。"""

    viewport_width: int | None = Field(default=None, ge=1, le=8192)
    viewport_height: int | None = Field(default=None, ge=1, le=8192)


class PageScreenshotJobResponse(SchemaBase):
    """页面截图任务响应。"""

    id: int
    job_group_id: str | None
    source: str
    page_id: int
    workspace_id: int | None
    project_id: int | None
    viewport_width: int
    viewport_height: int
    target_page_version_no: int
    config_hash: str
    status: PageScreenshotJobStatus
    attempt_count: int
    error_code: str | None
    error_message: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None


class PageScreenshotJobGroupResponse(BaseModel):
    """页面截图任务组聚合响应。"""

    job_group_id: str
    status: PageScreenshotJobGroupStatus
    requested_count: int
    pending_count: int
    running_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    cancelled_count: int
    page_ids: list[int] = Field(default_factory=list)
    jobs: list[PageScreenshotJobResponse] = Field(default_factory=list)
    failures: list[PageScreenshotBatchFailure] = Field(default_factory=list)


class PageComponentResourceItem(SchemaBase):
    """页面组件资源索引项，记录组件的参数名和值。"""

    component_name: str
    resource_attr: str
    resource_name: str


class PageCurrentComponentIndex(SchemaBase):
    """页面当前版本的组件索引响应，包含组件集合与资源集合。"""

    page_id: int
    current_version_no: int
    page_version_id: int | None
    components: list[str]
    resources: list[PageComponentResourceItem]


class PageModuleDependencyItem(SchemaBase):
    """页面当前版本的源码依赖项。"""

    dependency_kind: str
    component_code: str | None = None
    component_version_no: int | None = None
    runtime_module_path: str | None = None
    runtime_kit_name: str | None = None
    runtime_kit_base_name: str | None = None
    runtime_kit_version_no: int | None = None
    runtime_kit_import_path: str | None = None


class PageCurrentModuleDependencies(SchemaBase):
    """页面当前版本的源码依赖索引响应。"""

    page_id: int
    current_version_no: int
    page_version_id: int | None
    dependencies: list[PageModuleDependencyItem]
