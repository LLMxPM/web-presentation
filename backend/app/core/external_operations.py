"""文件功能：集中定义 External API 统一操作注册表与权限元数据，作为系统能力、API 鉴权、操作手册和防漂移测试的单一事实源。"""

from __future__ import annotations

from dataclasses import dataclass
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
        "guides.read", (), is_public=False, description="查询平台操作参数 Schema 与使用手册"
    ),
    "validate.code": ExternalOperationSpec(
        "validate.code",
        ("page:read", "component:read"),
        is_public=False,
        description="独立校验页面或组件源码语法与 Runtime Kit 依赖契约",
        scope_mode="any",
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

    # Page
    "page.list": ExternalOperationSpec(
        "page.list", ("page:read",), description="查询项目页面列表"
    ),
    "page.get": ExternalOperationSpec(
        "page.get", ("page:read",), description="获取页面详情、Vue 源码、依赖或历史版本"
    ),
    "page.update": ExternalOperationSpec(
        "page.update", ("page:write",), requires_idempotency_key=True, description="更新页面元数据"
    ),
    "page.archive": ExternalOperationSpec(
        "page.archive", ("page:write",), requires_idempotency_key=True, description="归档页面"
    ),
    "page.screenshot.latest": ExternalOperationSpec(
        "page.screenshot.latest",
        ("page:read", "preview:run"),
        description="获取页面最新截图",
    ),


    # Component
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
        "component.update", ("component:write",), requires_idempotency_key=True, description="更新组件元数据"
    ),
    "component.archive": ExternalOperationSpec(
        "component.archive", ("component:write",), requires_idempotency_key=True, description="归档工作空间组件"
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

    # Jobs (Build & Mutation)
    "jobs.build.start": ExternalOperationSpec(
        "jobs.build.start", ("build:run",), requires_idempotency_key=True, description="提交项目静态构建发布任务"
    ),
    "jobs.build.status": ExternalOperationSpec(
        "jobs.build.status", ("build:run",), description="查询构建任务状态与日志"
    ),

    "jobs.mutation.page.create": ExternalOperationSpec(
        "jobs.mutation.page.create", ("page:write",), requires_idempotency_key=True, description="提交页面异步创建/源码编辑重任务"
    ),
    "jobs.mutation.page.status": ExternalOperationSpec(
        "jobs.mutation.page.status", ("page:read",), description="查询页面 Mutation 任务状态与诊断"
    ),
    "jobs.mutation.page.cancel": ExternalOperationSpec(
        "jobs.mutation.page.cancel", ("page:write",), description="取消页面 Mutation 任务"
    ),
    "jobs.mutation.component.create": ExternalOperationSpec(
        "jobs.mutation.component.create", ("component:write",), requires_idempotency_key=True, description="提交组件异步创建/源码编辑重任务"
    ),
    "jobs.mutation.component.status": ExternalOperationSpec(
        "jobs.mutation.component.status", ("component:read",), description="查询组件 Mutation 任务状态与诊断"
    ),
    "jobs.mutation.component.cancel": ExternalOperationSpec(
        "jobs.mutation.component.cancel", ("component:write",), description="取消组件 Mutation 任务"
    ),
}

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
    "build:run",
    "workspace:read",
}


def get_operation_spec(key: str) -> ExternalOperationSpec | None:
    """获取指定操作规格；不存在时返回 None。"""

    return OPERATION_REGISTRY.get(key)
