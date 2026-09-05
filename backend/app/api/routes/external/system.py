"""文件功能：提供 External API v1 系统版本、健康检查、当前身份和页面/组件开发规范接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.external_api import (
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
- `component_type` 的规范值为 `content`、`page`、`atomic`。
- 兼容别名：`card`、`section`、`custom` 归一化为 `content`；`template` 归一化为 `page`；`atom`、`basic` 归一化为 `atomic`。
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
            "all_workspaces": auth.all_workspaces,
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
        if not auth.all_workspaces and ws.id not in auth.workspace_ids:
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
