"""文件功能：提供 External API v1 系统版本、健康检查、当前身份 whoami、页面/组件开发规范与操作使用指南接口。"""

from __future__ import annotations

from importlib import import_module
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.external_operations import OPERATION_REGISTRY
from app.db.session import get_db_session
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.external_api import (
    ExternalGuideResponse,
    ExternalGuideOperationDetail,
    ExternalGuideOperationIndexItem,
    ExternalStandardResponse,
    ExternalSystemHealthResponse,
    ExternalSystemVersionResponse,
    ExternalWhoAmIResponse,
)
from app.services.redis_runtime_client import get_redis_runtime_client

router = APIRouter()

PAGE_STANDARDS_DOC = """# 演示文稿页面开发规范 (Page Standards)

## 1. 基础规范
- 页面必须为合法的 Single File Component (Vue 3 SFC `<template>`, `<script setup>`, `<style scoped>`)。
- 采用 TailwindCSS 或 `@runtime-kit` 提供的样式令牌。
- 页面导出默认必须通过标准运行时容器渲染。

## 2. 依赖引入规范
- 仅允许引入 `@runtime-kit` 公开版本化能力或 `@workspace-components/<name>` 声明组件。
- 不得直接访问 `window` 未受控全局变量或执行恶意 DOM 操作。
"""

COMPONENT_STANDARDS_DOC = """# 工作空间组件开发规范 (Component Standards)

## 1. 基础规范
- 组件必须为 Vue 3 SFC 结构，使用 `<script setup lang="ts">`。
- 组件必须声明明确的 `props` 与可选 `previewSchema`。

## 2. 类型与 Preview Schema
- `component_type`: `card`, `section`, `template`, `custom`。
- `previewSchema`: 遵循 JSON Schema 规范，用于在 Editor 中提供属性表单编辑与预览 mock 数据。
"""


@router.get("/system/version", response_model=ExternalSystemVersionResponse)
async def get_system_version() -> ExternalSystemVersionResponse:
    """获取服务端系统与 API 版本信息。"""

    settings = get_settings()
    return ExternalSystemVersionResponse(
        version=settings.app_version,
        api_version="v1",
        app_name=settings.app_name,
    )


@router.get("/system/health", response_model=ExternalSystemHealthResponse)
async def get_system_health(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalSystemHealthResponse:
    """服务健康检查探活（检查数据库与 Redis）。"""

    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        get_redis_runtime_client().ping()
    except Exception:
        redis_ok = False
    overall_status = "ok" if (db_ok and redis_ok) else ("degraded" if (db_ok or redis_ok) else "error")

    return ExternalSystemHealthResponse(
        status=overall_status,
        database=db_ok,
        redis=redis_ok,
    )


@router.get("/auth/whoami", response_model=ExternalWhoAmIResponse)
async def get_auth_whoami(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("auth.whoami"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalWhoAmIResponse:
    """查询当前 PAT 令牌身份与授权工作空间。"""

    user_info = {
        "id": auth.user.id,
        "username": auth.user.username,
        "display_name": auth.user.display_name,
        "role": auth.user.role,
        "status": auth.user.status,
    }

    token_info = None
    if auth.token is not None:
        token_info = {
            "id": auth.token_id,
            "name": auth.token.name,
            "token_public_id": auth.token_public_id,
            "scopes": sorted(auth.scopes),
            "expires_at": auth.token.expires_at,
        }

    # 查询用户加入的活跃工作空间
    stmt = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == auth.user.id,
            WorkspaceMember.status == "active",
            Workspace.status == "active",
        )
    )
    results = (await session.execute(stmt)).all()
    workspaces = []
    for ws, role in results:
        # 若 PAT 限制了工作空间，过滤非绑定空间
        if auth.workspace_ids and ws.id not in auth.workspace_ids:
            continue
        workspaces.append(
            {
                "id": ws.id,
                "code": ws.code,
                "name": ws.name,
                "role": role,
            }
        )

    return ExternalWhoAmIResponse(
        user=user_info,
        token=token_info,
        workspaces=workspaces,
    )


@router.get("/standards/page", response_model=ExternalStandardResponse)
async def get_page_standards(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("standards.page"))],
) -> ExternalStandardResponse:
    """获取页面开发标准 Markdown 规范。"""

    return ExternalStandardResponse(
        standard_type="page",
        markdown=PAGE_STANDARDS_DOC,
    )


@router.get("/standards/component", response_model=ExternalStandardResponse)
async def get_component_standards(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("standards.component"))],
) -> ExternalStandardResponse:
    """获取工作空间组件开发标准 Markdown 规范。"""

    return ExternalStandardResponse(
        standard_type="component",
        markdown=COMPONENT_STANDARDS_DOC,
    )


@router.get("/guides", response_model=ExternalGuideResponse)
async def get_operation_guides(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("guides.read"))],
) -> ExternalGuideResponse:
    """查询平台操作参数规格与使用手册。"""

    guide_items: list[ExternalGuideOperationIndexItem] = []
    for key, spec in OPERATION_REGISTRY.items():
        guide_items.append(
            ExternalGuideOperationIndexItem(
                operation_key=spec.operation_key,
                operation_revision=spec.operation_revision,
                description=spec.description,
                scopes=list(spec.scopes),
                scope_mode=spec.scope_mode,
                is_public=spec.is_public,
                exempt_workspace_header=spec.exempt_workspace_header,
                requires_idempotency_key=spec.requires_idempotency_key,
                detail_url=f"/api/v1/guides/{key}",
            )
        )

    return ExternalGuideResponse(operations=guide_items)


@router.get("/guides/{operation_key}", response_model=ExternalGuideOperationDetail)
async def get_operation_guide_detail(
    operation_key: str,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("guides.read"))],
) -> ExternalGuideOperationDetail:
    """返回单项 operation 的版本化 HTTP 和 JSON Schema 契约。"""

    spec = OPERATION_REGISTRY.get(operation_key)
    if spec is None:
        raise AppException(
            status_code=404,
            code="GUIDE_OPERATION_NOT_FOUND",
            detail=f"未找到 operation '{operation_key}' 的公开指南。",
        )
    required_headers = [] if spec.is_public else ["Authorization"]
    if not spec.is_public and not spec.exempt_workspace_header:
        required_headers.append("X-Workspace-ID")
    if spec.requires_idempotency_key:
        required_headers.append("Idempotency-Key")
    error_codes = list(spec.error_codes)
    if not spec.is_public:
        error_codes.extend(["EXTERNAL_AUTH_REQUIRED", "INVALID_ACCESS_TOKEN"])
    if spec.scopes:
        error_codes.append("INSUFFICIENT_SCOPE")
    if not spec.is_public and not spec.exempt_workspace_header:
        error_codes.extend(["WORKSPACE_HEADER_REQUIRED", "WORKSPACE_NOT_AUTHORIZED"])
    if spec.requires_idempotency_key:
        error_codes.extend([
            "IDEMPOTENCY_KEY_REQUIRED",
            "INVALID_IDEMPOTENCY_KEY",
            "CONCURRENT_MUTATION_IN_PROGRESS",
        ])
    return ExternalGuideOperationDetail(
        operation_key=spec.operation_key,
        operation_revision=spec.operation_revision,
        description=spec.description,
        method=spec.http_method,
        path=spec.path_template,
        scopes=list(spec.scopes),
        scope_mode=spec.scope_mode,
        required_headers=required_headers,
        requires_idempotency_key=spec.requires_idempotency_key,
        success_statuses=list(spec.success_statuses),
        error_codes=list(dict.fromkeys(error_codes)),
        request_schema=_resolve_model_schema(spec.request_model),
        response_schema=_resolve_model_schema(spec.response_model),
    )


def _resolve_model_schema(model_path: str | None) -> dict[str, Any] | None:
    """按注册表中的模型路径加载 Pydantic JSON Schema，避免复制第二份参数定义。"""

    if not model_path:
        return None
    module_name, model_name = model_path.rsplit(".", 1)
    model = getattr(import_module(module_name), model_name)
    return model.model_json_schema()
