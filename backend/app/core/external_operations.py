"""文件功能：集中定义 External API 统一操作注册表与权限元数据，作为系统能力、API 鉴权、操作手册和防漂移测试的单一事实源。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Tuple


@dataclass(frozen=True)
class ExternalOperationSpec:
    """External API 外部操作元数据规格。"""

    operation_key: str
    scopes: Tuple[str, ...]
    is_public: bool = False
    is_external: bool = True
    exempt_workspace_header: bool = False
    requires_idempotency_key: bool = False
    description: str = ""
    scope_mode: Literal["all", "any"] = "all"
    operation_revision: int = 1
    http_method: str = "GET"
    path_template: str = ""
    request_model: str | None = None
    response_model: str | None = None
    success_statuses: Tuple[int, ...] = (200,)
    error_codes: Tuple[str, ...] = ()


OPERATION_REGISTRY: dict[str, ExternalOperationSpec] = {
    # System
    "system.version": ExternalOperationSpec(
        "system.version", (), is_public=True, description="获取服务端版本信息"
    ),
    "system.health": ExternalOperationSpec(
        "system.health", (), is_public=True, description="服务健康检查探活"
    ),
    "system.capabilities": ExternalOperationSpec(
        "system.capabilities", (), is_public=False, description="查询外部 API 功能矩阵与系统限制"
    ),

    # Auth & Workspace & Operations
    "auth.whoami": ExternalOperationSpec(
        "auth.whoami", (), is_public=False, exempt_workspace_header=True, description="查询当前 PAT 身份及授权空间"
    ),
    "workspace.list": ExternalOperationSpec(
        "workspace.list", ("workspace:read",), is_public=False, exempt_workspace_header=True, description="列出已授权的工作空间"
    ),
    "workspace.get": ExternalOperationSpec(
        "workspace.get", ("workspace:read",), is_public=False, description="获取工作空间详情与可用能力"
    ),
    "standards.page": ExternalOperationSpec(
        "standards.page", ("page:read",), is_public=False, description="获取页面开发标准 Markdown 规范"
    ),
    "standards.component": ExternalOperationSpec(
        "standards.component", ("component:read",), is_public=False, description="获取工作空间组件开发标准 Markdown 规范"
    ),
    "guides.read": ExternalOperationSpec(
        "guides.read",
        (),
        is_public=False,
        exempt_workspace_header=True,
        description="查询平台操作参数 Schema 与使用手册",
        path_template="/guides",
        response_model="app.schemas.external_api.ExternalGuideResponse",
    ),
    "validate.entity": ExternalOperationSpec(
        "validate.entity",
        ("page:read", "component:read"),
        description="校验页面或组件当前内容及候选内容",
        scope_mode="any",
        request_model="app.schemas.external_api.ExternalEntityValidationRequest",
        response_model="app.schemas.external_api.ExternalEntityValidationResponse",
    ),
    "runtime_kit.list": ExternalOperationSpec(
        "runtime_kit.list", ("workspace:read",), exempt_workspace_header=True, description="查询 Runtime Kit 公开能力目录"
    ),
    "runtime_kit.get": ExternalOperationSpec(
        "runtime_kit.get", ("workspace:read",), exempt_workspace_header=True, description="获取 Runtime Kit 能力详情"
    ),
    "font.list": ExternalOperationSpec(
        "font.list", ("asset:read",), description="查询工作空间注册字体"
    ),

    # Project
    "project.list": ExternalOperationSpec(
        "project.list", ("project:read",), description="查询项目列表"
    ),
    "project.get": ExternalOperationSpec(
        "project.get", ("project:read",), description="获取项目详情、配置或路由树"
    ),
    "project.create": ExternalOperationSpec(
        "project.create", ("project:write",), requires_idempotency_key=True, description="创建新项目"
    ),
    "project.update": ExternalOperationSpec(
        "project.update", ("project:write",), requires_idempotency_key=True, description="更新项目元数据、配置、样式或整树替换路由"
    ),
    "project.archive": ExternalOperationSpec(
        "project.archive", ("project:write",), requires_idempotency_key=True, description="归档项目"
    ),
    "project.configuration.get": ExternalOperationSpec(
        "project.configuration.get", ("project:read",), description="获取项目结构化配置",
        response_model="app.schemas.external_api.ExternalProjectConfigurationResponse",
    ),
    "project.configuration.update": ExternalOperationSpec(
        "project.configuration.update", ("project:write",), requires_idempotency_key=True, description="更新项目结构化配置",
        request_model="app.schemas.external_api.ExternalProjectConfigurationUpdateRequest", response_model="app.schemas.project.ProjectItem",
    ),
    "project.route.get": ExternalOperationSpec(
        "project.route.get", ("project:read",), description="获取项目路由树"
    ),
    "project.route.update": ExternalOperationSpec(
        "project.route.update", ("project:write",), requires_idempotency_key=True, description="整体替换项目路由树",
        request_model="app.schemas.project_route.ProjectRouteTreeWriteRequest", response_model="app.schemas.project_route.ProjectRouteTreeResponse",
    ),
    "project.apply_style": ExternalOperationSpec(
        "project.apply_style", ("project:write", "design-system:read"), requires_idempotency_key=True, description="将样式方案应用到项目",
        request_model="app.schemas.external_api.ExternalProjectApplyStyleRequest", response_model="app.schemas.project.ProjectItem",
    ),
    "project.build_assets.update": ExternalOperationSpec(
        "project.build_assets.update", ("project:write",), requires_idempotency_key=True, description="更新项目构建额外资源配置",
        request_model="app.schemas.external_api.ExternalProjectBuildAssetsRequest", response_model="app.schemas.project.ProjectItem",
    ),

    # Page
    "page.list": ExternalOperationSpec(
        "page.list", ("page:read",), description="查询项目页面列表"
    ),
    "page.get": ExternalOperationSpec(
        "page.get", ("page:read",), description="获取页面详情、Vue 源码、依赖或历史版本"
    ),
    "page.update": ExternalOperationSpec(
        "page.update",
        ("page:write",),
        requires_idempotency_key=True,
        description="更新页面标题、摘要或演讲备注",
        http_method="PATCH",
        path_template="/pages/{page_id}",
        request_model="app.schemas.external_api.ExternalPageMetadataUpdateRequest",
        response_model="app.schemas.page.PageItem",
        error_codes=("PAGE_NOT_FOUND", "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"),
    ),
    "page.archive": ExternalOperationSpec(
        "page.archive", ("page:write",), requires_idempotency_key=True, description="归档页面"
    ),
    "page.screenshot.latest": ExternalOperationSpec(
        "page.screenshot.latest",
        ("page:read", "preview:run"),
        description="获取页面最新截图",
    ),
    "page.create": ExternalOperationSpec(
        "page.create", ("page:write",), requires_idempotency_key=True, description="提交页面异步创建任务",
        http_method="POST", path_template="/pages", request_model="app.schemas.external_api.ExternalPageCreateMutationRequest", response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "page.copy": ExternalOperationSpec(
        "page.copy", ("page:write",), requires_idempotency_key=True, description="复制页面到目标项目",
        http_method="POST", path_template="/pages/{page_id}/copy", request_model="app.schemas.external_api.ExternalPageCopyRequest", response_model="app.schemas.page.PageItem", success_statuses=(201,),
    ),
    "page.edit": ExternalOperationSpec(
        "page.edit", ("page:write",), requires_idempotency_key=True, description="提交页面异步源码编辑任务",
        http_method="POST", path_template="/pages/{page_id}/edits", request_model="app.schemas.external_api.ExternalPageApplyEditsMutationRequest", response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "page.dependencies": ExternalOperationSpec(
        "page.dependencies", ("page:read",), description="查询页面当前版本依赖"
    ),
    "page.validate": ExternalOperationSpec(
        "page.validate", ("page:read",), description="校验页面当前或候选源码",
        request_model="app.schemas.external_api.ExternalEntityValidationRequest", response_model="app.schemas.external_api.ExternalEntityValidationResponse",
    ),


    # Component
    "component.create": ExternalOperationSpec(
        "component.create", ("component:write",), requires_idempotency_key=True, description="提交组件异步创建任务",
        http_method="POST", path_template="/components", request_model="app.schemas.external_api.ExternalComponentCreateMutationRequest", response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "component.list": ExternalOperationSpec(
        "component.list", ("component:read",), description="查询工作空间组件列表（支持 suggested/all 过滤）"
    ),
    "component.get": ExternalOperationSpec(
        "component.get", ("component:read",), description="获取组件详情、SFC 源码或历史版本"
    ),
    "component.publish": ExternalOperationSpec(
        "component.publish", ("component:write",), requires_idempotency_key=True, description="发布组件草稿为正式版本"
    ),
    "component.update": ExternalOperationSpec(
        "component.update",
        ("component:write",),
        requires_idempotency_key=True,
        description="更新组件名称或摘要",
        http_method="PATCH",
        path_template="/components/{component_id}",
        request_model="app.schemas.external_api.ExternalComponentMetadataUpdateRequest",
        response_model="app.schemas.component.WorkspaceComponentItem",
        error_codes=("COMPONENT_NOT_FOUND", "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"),
    ),
    "component.archive": ExternalOperationSpec(
        "component.archive", ("component:write",), requires_idempotency_key=True, description="归档工作空间组件"
    ),
    "component.dependencies": ExternalOperationSpec(
        "component.dependencies", ("component:read",), description="查询组件当前版本依赖", response_model="app.schemas.component.WorkspaceComponentCurrentDependencies",
    ),
    "component.edit": ExternalOperationSpec(
        "component.edit", ("component:write",), requires_idempotency_key=True, description="提交组件异步源码编辑任务",
        http_method="POST", path_template="/components/{component_id}/edits", request_model="app.schemas.external_api.ExternalComponentApplyEditsMutationRequest", response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "component.validate": ExternalOperationSpec(
        "component.validate", ("component:read",), description="校验组件当前或候选源码",
        request_model="app.schemas.external_api.ExternalEntityValidationRequest", response_model="app.schemas.external_api.ExternalEntityValidationResponse",
    ),

    # Asset
    "asset.list": ExternalOperationSpec(
        "asset.list", ("asset:read",), description="查询资产列表与标签"
    ),
    "asset.get": ExternalOperationSpec(
        "asset.get", ("asset:read",), description="获取资产详情或可编辑文本内容"
    ),
    "asset.upload": ExternalOperationSpec(
        "asset.upload", ("asset:write",), requires_idempotency_key=True, description="上传资产文件或图片"
    ),
    "asset.update": ExternalOperationSpec(
        "asset.update", ("asset:write",), requires_idempotency_key=True, description="更新可编辑资产内容或元数据"
    ),
    "asset.archive": ExternalOperationSpec(
        "asset.archive", ("asset:write",), requires_idempotency_key=True, description="归档资产"
    ),
    "asset.content.create": ExternalOperationSpec(
        "asset.content.create", ("asset:write",), requires_idempotency_key=True, description="创建文本内容资产",
        http_method="POST", path_template="/assets/content", request_model="app.schemas.external_api.ExternalAssetContentCreateRequest", response_model="app.schemas.asset.AssetResponse", success_statuses=(201,),
    ),
    "asset.content.get": ExternalOperationSpec(
        "asset.content.get", ("asset:read",), description="读取文本内容资产", response_model="app.schemas.asset.AssetContentResponse",
    ),
    "asset.content.update": ExternalOperationSpec(
        "asset.content.update", ("asset:write",), requires_idempotency_key=True, description="更新文本内容资产",
        http_method="PUT", path_template="/assets/{asset_id}/content", request_model="app.schemas.external_api.ExternalAssetContentUpdateRequest", response_model="app.schemas.asset.AssetResponse",
    ),
    "asset.content.preview": ExternalOperationSpec(
        "asset.content.preview", ("asset:read",), description="预览文本内容资产差异",
        http_method="POST", path_template="/assets/{asset_id}/content/preview", request_model="app.schemas.external_api.ExternalAssetContentPreviewRequest", response_model="app.schemas.asset.AssetContentPreviewResponse",
    ),
    "asset.copy": ExternalOperationSpec(
        "asset.copy", ("asset:write",), requires_idempotency_key=True, description="复制资产",
        http_method="POST", path_template="/assets/{asset_id}/copy", request_model="app.schemas.external_api.ExternalAssetCopyRequest", response_model="app.schemas.asset.AssetResponse", success_statuses=(201,),
    ),
    "asset.tags": ExternalOperationSpec(
        "asset.tags", ("asset:read",), description="查询资产标签",
    ),

    # Theme & Style
    "theme.list": ExternalOperationSpec(
        "theme.list", ("design-system:read",), description="查询主题列表"
    ),
    "theme.get": ExternalOperationSpec(
        "theme.get", ("design-system:read",), description="获取主题详情"
    ),
    "theme.create": ExternalOperationSpec(
        "theme.create", ("design-system:write",), requires_idempotency_key=True, description="创建新主题"
    ),
    "theme.update": ExternalOperationSpec(
        "theme.update", ("design-system:write",), requires_idempotency_key=True, description="更新主题名称、描述或色板（禁止修改 key）"
    ),
    "theme.copy": ExternalOperationSpec(
        "theme.copy", ("design-system:write",), requires_idempotency_key=True, description="复制主题"
    ),
    "theme.archive": ExternalOperationSpec(
        "theme.archive", ("design-system:write",), requires_idempotency_key=True, description="归档主题（带引用冲突校验）"
    ),

    "style.list": ExternalOperationSpec(
        "style.list", ("design-system:read",), description="查询样式方案列表"
    ),
    "style.get": ExternalOperationSpec(
        "style.get", ("design-system:read",), description="获取样式方案详情与配置"
    ),
    "style.create": ExternalOperationSpec(
        "style.create", ("design-system:write",), requires_idempotency_key=True, description="创建新样式方案"
    ),
    "style.update": ExternalOperationSpec(
        "style.update", ("design-system:write",), requires_idempotency_key=True, description="更新样式方案元数据或配置"
    ),
    "style.copy": ExternalOperationSpec(
        "style.copy", ("design-system:write",), requires_idempotency_key=True, description="复制样式方案"
    ),
    "style.archive": ExternalOperationSpec(
        "style.archive", ("design-system:write",), requires_idempotency_key=True, description="归档样式方案"
    ),

    # Mutation Jobs
    "jobs.mutation.page.create": ExternalOperationSpec(
        "jobs.mutation.page.create", ("page:write",), requires_idempotency_key=True, description="提交页面异步创建任务",
        http_method="POST", path_template="/jobs/mutations/pages",
        request_model="app.schemas.external_api.ExternalPageCreateMutationRequest",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "jobs.mutation.page.edit": ExternalOperationSpec(
        "jobs.mutation.page.edit", ("page:write",), requires_idempotency_key=True, description="提交页面异步源码编辑任务",
        http_method="POST", path_template="/jobs/mutations/pages/edits",
        request_model="app.schemas.external_api.ExternalPageApplyEditsMutationRequest",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "jobs.mutation.page.status": ExternalOperationSpec(
        "jobs.mutation.page.status", ("page:read",), description="查询页面 Mutation 任务状态与诊断"
    ),
    "jobs.mutation.page.cancel": ExternalOperationSpec(
        "jobs.mutation.page.cancel", ("page:write",), requires_idempotency_key=True, description="取消页面 Mutation 任务",
        http_method="POST", path_template="/jobs/mutations/{job_id}/cancel",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(200, 202),
        error_codes=("MUTATION_JOB_NOT_FOUND", "MUTATION_JOB_NOT_CANCELABLE"),
    ),
    "jobs.mutation.page.retry": ExternalOperationSpec(
        "jobs.mutation.page.retry", ("page:write",), requires_idempotency_key=True, description="重试可重试失败的页面 Mutation 任务",
        http_method="POST", path_template="/jobs/mutations/{job_id}/retry",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
        error_codes=("MUTATION_JOB_NOT_FOUND", "MUTATION_JOB_NOT_RETRYABLE"),
    ),
    "jobs.mutation.component.create": ExternalOperationSpec(
        "jobs.mutation.component.create", ("component:write",), requires_idempotency_key=True, description="提交组件异步创建任务",
        http_method="POST", path_template="/jobs/mutations/components",
        request_model="app.schemas.external_api.ExternalComponentCreateMutationRequest",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "jobs.mutation.component.edit": ExternalOperationSpec(
        "jobs.mutation.component.edit", ("component:write",), requires_idempotency_key=True, description="提交组件异步源码编辑任务",
        http_method="POST", path_template="/jobs/mutations/components/edits",
        request_model="app.schemas.external_api.ExternalComponentApplyEditsMutationRequest",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "jobs.mutation.component.metadata": ExternalOperationSpec(
        "jobs.mutation.component.metadata", ("component:write",), requires_idempotency_key=True, description="提交组件元数据异步重校验任务",
        http_method="POST", path_template="/jobs/mutations/components/metadata",
        request_model="app.schemas.external_api.ExternalComponentMetadataMutationRequest",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
    ),
    "jobs.mutation.component.status": ExternalOperationSpec(
        "jobs.mutation.component.status", ("component:read",), description="查询组件 Mutation 任务状态与诊断"
    ),
    "jobs.mutation.component.cancel": ExternalOperationSpec(
        "jobs.mutation.component.cancel", ("component:write",), requires_idempotency_key=True, description="取消组件 Mutation 任务",
        http_method="POST", path_template="/jobs/mutations/{job_id}/cancel",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(200, 202),
        error_codes=("MUTATION_JOB_NOT_FOUND", "MUTATION_JOB_NOT_CANCELABLE"),
    ),
    "jobs.mutation.component.retry": ExternalOperationSpec(
        "jobs.mutation.component.retry", ("component:write",), requires_idempotency_key=True, description="重试可重试失败的组件 Mutation 任务",
        http_method="POST", path_template="/jobs/mutations/{job_id}/retry",
        response_model="app.schemas.external_api.ExternalMutationJobResponse", success_statuses=(202,),
        error_codes=("MUTATION_JOB_NOT_FOUND", "MUTATION_JOB_NOT_RETRYABLE"),
    ),
}

# 为全部稳定 operation 冻结一个用于 Guides 的主路径；同一读取 operation 的附加视图
# 继续由资源文档描述，不把内部路由扫描结果当作公开契约。
_OPERATION_HTTP_CONTRACTS: dict[str, tuple[str, str]] = {
    "system.version": ("GET", "/system/version"),
    "system.health": ("GET", "/system/health"),
    "system.capabilities": ("GET", "/workspaces/{workspace_id}/capabilities"),
    "auth.whoami": ("GET", "/auth/whoami"),
    "workspace.list": ("GET", "/workspaces"),
    "workspace.get": ("GET", "/workspaces/{workspace_id}"),
    "standards.page": ("GET", "/standards/page"),
    "standards.component": ("GET", "/standards/component"),
    "guides.read": ("GET", "/guides"),
    "validate.entity": ("POST", "/validate/entity"),
    "runtime_kit.list": ("GET", "/runtime-kit"),
    "runtime_kit.get": ("GET", "/runtime-kit/{item}"),
    "font.list": ("GET", "/fonts"),
    "project.list": ("GET", "/projects"),
    "project.get": ("GET", "/projects/{project_id}"),
    "project.create": ("POST", "/projects"),
    "project.update": ("PATCH", "/projects/{project_id}"),
    "project.archive": ("POST", "/projects/{project_id}/archive"),
    "project.configuration.get": ("GET", "/projects/{project_id}/configuration"),
    "project.configuration.update": ("PUT", "/projects/{project_id}/configuration"),
    "project.route.get": ("GET", "/projects/{project_id}/route-tree"),
    "project.route.update": ("PUT", "/projects/{project_id}/route-tree"),
    "project.apply_style": ("POST", "/projects/{project_id}/apply-style"),
    "project.build_assets.update": ("PUT", "/projects/{project_id}/build-assets"),
    "page.list": ("GET", "/projects/{project_id}/pages"),
    "page.get": ("GET", "/pages/{page_id}"),
    "page.update": ("PATCH", "/pages/{page_id}"),
    "page.create": ("POST", "/pages"),
    "page.copy": ("POST", "/pages/{page_id}/copy"),
    "page.edit": ("POST", "/pages/{page_id}/edits"),
    "page.dependencies": ("GET", "/pages/{page_id}/dependencies"),
    "page.validate": ("POST", "/pages/{page_id}/validate"),
    "page.archive": ("POST", "/pages/{page_id}/archive"),
    "page.screenshot.latest": ("GET", "/pages/{page_id}/screenshot"),
    "component.list": ("GET", "/components"),
    "component.create": ("POST", "/components"),
    "component.get": ("GET", "/components/{component_id}"),
    "component.publish": ("POST", "/components/{component_id}/publish"),
    "component.update": ("PATCH", "/components/{component_id}"),
    "component.dependencies": ("GET", "/components/{component_id}/dependencies"),
    "component.edit": ("POST", "/components/{component_id}/edits"),
    "component.validate": ("POST", "/components/{component_id}/validate"),
    "component.archive": ("POST", "/components/{component_id}/archive"),
    "asset.list": ("GET", "/assets"),
    "asset.get": ("GET", "/assets/{asset_id}"),
    "asset.upload": ("POST", "/assets"),
    "asset.update": ("PATCH", "/assets/{asset_id}"),
    "asset.archive": ("POST", "/assets/{asset_id}/archive"),
    "asset.content.create": ("POST", "/assets/content"),
    "asset.content.get": ("GET", "/assets/{asset_id}/content"),
    "asset.content.update": ("PUT", "/assets/{asset_id}/content"),
    "asset.content.preview": ("POST", "/assets/{asset_id}/content/preview"),
    "asset.copy": ("POST", "/assets/{asset_id}/copy"),
    "asset.tags": ("GET", "/assets/tags"),
    "theme.list": ("GET", "/themes"),
    "theme.get": ("GET", "/themes/{theme_id}"),
    "theme.create": ("POST", "/themes"),
    "theme.update": ("PATCH", "/themes/{theme_id}"),
    "theme.copy": ("POST", "/themes/{theme_id}/copy"),
    "theme.archive": ("POST", "/themes/{theme_id}/archive"),
    "style.list": ("GET", "/styles"),
    "style.get": ("GET", "/styles/{style_id}"),
    "style.create": ("POST", "/styles"),
    "style.update": ("PATCH", "/styles/{style_id}"),
    "style.copy": ("POST", "/styles/{style_id}/copy"),
    "style.archive": ("POST", "/styles/{style_id}/archive"),
    "jobs.mutation.page.create": ("POST", "/jobs/mutations/pages"),
    "jobs.mutation.page.edit": ("POST", "/jobs/mutations/pages/edits"),
    "jobs.mutation.page.status": ("GET", "/jobs/mutations/{job_id}"),
    "jobs.mutation.page.cancel": ("POST", "/jobs/mutations/{job_id}/cancel"),
    "jobs.mutation.page.retry": ("POST", "/jobs/mutations/{job_id}/retry"),
    "jobs.mutation.component.create": ("POST", "/jobs/mutations/components"),
    "jobs.mutation.component.edit": ("POST", "/jobs/mutations/components/edits"),
    "jobs.mutation.component.metadata": ("POST", "/jobs/mutations/components/metadata"),
    "jobs.mutation.component.status": ("GET", "/jobs/mutations/{job_id}"),
    "jobs.mutation.component.cancel": ("POST", "/jobs/mutations/{job_id}/cancel"),
    "jobs.mutation.component.retry": ("POST", "/jobs/mutations/{job_id}/retry"),
}

if set(_OPERATION_HTTP_CONTRACTS) != set(OPERATION_REGISTRY):
    raise RuntimeError("External operation 注册表与 HTTP 契约映射不完整。")
for _operation_key, (_method, _path) in _OPERATION_HTTP_CONTRACTS.items():
    OPERATION_REGISTRY[_operation_key] = replace(
        OPERATION_REGISTRY[_operation_key],
        http_method=_method,
        path_template=_path,
    )

OPERATION_SCOPE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    k: v.scopes for k, v in OPERATION_REGISTRY.items()
}


ALL_VALID_SCOPES: set[str] = {
    "project:read",
    "project:write",
    "page:read",
    "page:write",
    "component:read",
    "component:write",
    "asset:read",
    "asset:write",
    "design-system:read",
    "design-system:write",
    "preview:run",
    "workspace:read",
}


def get_operation_spec(key: str) -> ExternalOperationSpec | None:
    """获取指定操作规格；不存在时返回 None。"""

    return OPERATION_REGISTRY.get(key)
