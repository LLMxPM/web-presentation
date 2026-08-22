"""文件功能：定义 External API v1 专属请求/响应 DTO、错误模型与能力清单。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class ExternalErrorDetail(BaseModel):
    """External API 统一错误响应模型。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="业务错误码")
    message: str = Field(..., description="错误详细描述")
    retryable: bool = Field(default=False, description="是否为临时性可重试错误")
    details: dict[str, Any] | None = Field(default=None, description="错误补充上下文")


class ExternalEnvelope(BaseModel, Generic[T]):
    """External API 统一响应信封（可选，常规直接返回 DTO 并附带 X-Request-ID）。"""

    model_config = ConfigDict(extra="forbid")

    data: T
    request_id: str | None = None


class ExternalCapabilitiesResponse(BaseModel):
    """能力发现响应模型。"""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="v1", description="API 版本")
    workspace_id: int = Field(..., description="当前工作空间 ID")
    scopes: list[str] = Field(..., description="当前 Token 拥有的权限 Scopes")
    operations: list[str] = Field(..., description="当前 Token 在当前工作空间允许执行的操作列表")


class ExternalBatchArchiveRequest(BaseModel):
    """批量归档请求模型。"""

    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(..., min_length=1, max_length=100, description="待归档实体 ID 列表")
    reason: str | None = Field(default=None, max_length=500, description="归档原因")


class ExternalBatchArchiveResponse(BaseModel):
    """批量归档响应模型。"""

    model_config = ConfigDict(extra="forbid")

    archived_ids: list[int]
    failed_ids: list[int]
    total: int


class ExternalPageMetadataUpdateRequest(BaseModel):
    """External API 页面轻量元数据更新请求，禁止绕过 Mutation 写入源码。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=500)
    speaker_notes: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def validate_partial_update(self) -> "ExternalPageMetadataUpdateRequest":
        """要求至少提供一个字段，并禁止把必填标题显式清空。"""

        if not self.model_fields_set:
            raise ValueError("页面元数据更新至少需要提供一个字段。")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title 不能为 null。")
        return self


class ExternalComponentMetadataUpdateRequest(BaseModel):
    """External API 组件轻量元数据更新请求，结构与源码字段继续走 Mutation。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_partial_update(self) -> "ExternalComponentMetadataUpdateRequest":
        """要求至少提供一个字段，并禁止把组件名称显式清空。"""

        if not self.model_fields_set:
            raise ValueError("组件元数据更新至少需要提供一个字段。")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name 不能为 null。")
        return self


class ExternalPageCreateMutationRequest(BaseModel):
    """页面创建异步 Mutation 任务请求。"""

    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(..., description="目标项目 ID")
    name: str = Field(..., min_length=1, max_length=128, description="页面名称")
    source_code: str = Field(..., description="页面完整 Vue 源码")
    description: str | None = Field(default=None, max_length=500, description="页面描述")


class ExternalPageApplyEditsMutationRequest(BaseModel):
    """页面结构化编辑异步 Mutation 任务请求。"""

    model_config = ConfigDict(extra="forbid")

    page_id: int = Field(..., description="目标页面 ID")
    base_version_no: int = Field(..., ge=1, description="基准版本号 (乐观锁并发控制)")
    edits: list[dict[str, Any]] = Field(..., min_length=1, description="结构化替换/修改指令列表")


class ExternalComponentCreateMutationRequest(BaseModel):
    """组件创建异步 Mutation 任务请求。"""

    model_config = ConfigDict(extra="forbid")

    workspace_id: int = Field(..., description="目标工作空间 ID")
    import_name: str = Field(..., min_length=1, max_length=64, description="组件导入名 (PascalCase)")
    name: str = Field(..., min_length=1, max_length=128, description="组件展示名称")
    component_type: str = Field(default="content", description="组件类型 (content, page, atomic, 或别名 card, section, template, custom)")
    source_code: str = Field(..., description="组件完整 Vue 源码")
    description: str | None = Field(default=None, max_length=500, description="组件描述")
    preview_schema: dict[str, Any] | None = Field(default=None, description="组件预览 Props Schema")


class ExternalComponentApplyEditsMutationRequest(BaseModel):
    """组件结构化编辑异步 Mutation 任务请求。"""

    model_config = ConfigDict(extra="forbid")

    component_id: int = Field(..., description="目标工作空间组件 ID")
    base_version_no: int = Field(..., ge=0, description="基准版本号 (乐观锁并发控制)")
    base_draft_hash: str | None = Field(default=None, min_length=1, description="组件草稿 SHA-256 指纹")
    edits: list[dict[str, Any]] = Field(..., min_length=1, description="结构化替换/修改指令列表")


class ExternalMutationJobResponse(BaseModel):
    """异步变更任务状态响应模型。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., description="异步任务公开标识 (UUID)")
    job_type: str = Field(..., description="任务类型 (page_create, page_edit, component_create, component_edit)")
    workspace_id: int = Field(..., description="所属工作空间 ID")
    target_id: int | None = Field(default=None, description="操作目标实体 ID")
    status: Literal["pending", "running", "succeeded", "failed", "canceled"] = Field(
        ..., description="任务当前状态"
    )
    attempt_count: int = Field(..., description="已执行的自动重试次数，不包含首次执行")
    max_attempts: int = Field(..., description="允许的最大执行次数，包含首次执行")
    next_attempt_at: datetime | None = Field(default=None, description="下次重试时间")
    last_error_code: str | None = Field(default=None, description="最近一次错误码")
    cancel_requested_at: datetime | None = Field(default=None, description="协作式取消请求时间")
    retry_of_job_id: str | None = Field(default=None, description="人工重试来源任务公开标识")
    result: dict[str, Any] | None = Field(default=None, description="任务成功后的输出结果")
    error: ExternalErrorDetail | None = Field(default=None, description="任务失败或取消时的结构化错误")
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ExternalValidateCodeRequest(BaseModel):
    """源码独立校验请求。"""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["page", "component"] = Field(..., description="待校验实体类型")
    source_code: str = Field(..., description="待校验源码")
    preview_schema: dict[str, Any] | None = Field(default=None, description="组件预览 Props Schema（仅组件）")


class ExternalValidateCodeResponse(BaseModel):
    """源码独立校验响应。"""

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(..., description="是否通过语法与 Runtime Kit 校验")
    errors: list[str] = Field(default_factory=list, description="校验失败时的错误信息列表")
    warnings: list[str] = Field(default_factory=list, description="非致命警告信息列表")
    imports: list[str] = Field(default_factory=list, description="源码中引用的 Runtime Kit / 组件导入清单")


class ExternalProjectCreateRequest(BaseModel):
    """External API 项目创建请求（workspace_id 优先使用 Header 中的 X-Workspace-ID）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128, description="项目名称")
    description: str | None = Field(default=None, max_length=2000, description="项目描述")
    status: str = Field(default="active", description="项目状态")
    configuration: dict[str, Any] | None = Field(default=None, description="项目展示配置")
    build_extra_assets_json: dict[str, Any] | None = Field(default=None, description="构建额外打包资源配置")


class ExternalThemeCreateRequest(BaseModel):
    """External API 主题创建请求（palette 缺省时自动填充默认调色板）。"""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, max_length=64, description="主题唯一标识 (例如 light-corporate)")
    name: str = Field(..., min_length=1, max_length=128, description="主题展示名称")
    description: str | None = Field(default=None, max_length=2000, description="主题描述")
    palette: dict[str, Any] | None = Field(default=None, description="主题色板配置")


class ExternalStyleCreateRequest(BaseModel):
    """External API 样式创建请求（key 缺省时自动生成）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128, description="样式方案名称")
    key: str | None = Field(default=None, max_length=64, description="样式唯一标识")
    description: str | None = Field(default=None, max_length=2000, description="样式描述")
    theme_key: str | None = Field(default=None, description="绑定主题 key")


class ExternalSystemVersionResponse(BaseModel):
    """系统版本信息响应。"""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(..., description="平台后端版本")
    api_version: str = Field(default="v1", description="外部 API 接口版本")
    app_name: str = Field(..., description="应用名称")


class ExternalSystemHealthResponse(BaseModel):
    """系统健康状态响应。"""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok", description="整体健康状态 (ok, degraded, error)")
    database: bool = Field(default=True, description="数据库连接状态")
    redis: bool = Field(default=True, description="Redis 连接状态")


class ExternalWhoAmIResponse(BaseModel):
    """当前鉴权身份与授权工作空间。"""

    model_config = ConfigDict(extra="forbid")

    user: dict[str, Any] = Field(..., description="当前用户信息")
    token: dict[str, Any] | None = Field(default=None, description="当前 Token 信息")
    workspaces: list[dict[str, Any]] = Field(default_factory=list, description="授权访问的工作空间列表")


class ExternalStandardResponse(BaseModel):
    """标准规范响应。"""

    model_config = ConfigDict(extra="forbid")

    standard_type: str = Field(..., description="规范类型 (page / component)")
    markdown: str = Field(..., description="标准规范 Markdown 文本")


class ExternalGuideOperationIndexItem(BaseModel):
    """操作指南索引项。"""

    model_config = ConfigDict(extra="forbid")

    operation_key: str
    operation_revision: int = 1
    description: str
    scopes: list[str] = Field(default_factory=list)
    scope_mode: Literal["all", "any"] = "all"
    is_public: bool = False
    exempt_workspace_header: bool = False
    requires_idempotency_key: bool = False
    detail_url: str


class ExternalGuideResponse(BaseModel):
    """版本化 API 操作指南索引响应。"""

    model_config = ConfigDict(extra="forbid")

    api_version: Literal["v1"] = "v1"
    guide_schema_version: Literal[1] = 1
    operations: list[ExternalGuideOperationIndexItem] = Field(default_factory=list)


class ExternalGuideOperationDetail(BaseModel):
    """单项 External operation 的精确 HTTP 与 JSON Schema 契约。"""

    model_config = ConfigDict(extra="forbid")

    api_version: Literal["v1"] = "v1"
    guide_schema_version: Literal[1] = 1
    operation_key: str
    operation_revision: int = 1
    description: str
    method: str
    path: str
    scopes: list[str] = Field(default_factory=list)
    scope_mode: Literal["all", "any"] = "all"
    required_headers: list[str] = Field(default_factory=list)
    requires_idempotency_key: bool = False
    success_statuses: list[int] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None

