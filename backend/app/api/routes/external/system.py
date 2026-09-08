"""文件功能：提供 External API v1 系统版本、健康检查、当前身份和页面/组件开发规范接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.code_standards import get_default_code_standard
from app.ai.tool_specs import AGENT_COORDINATOR_AGENT_ID
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
from app.services.ai_agent_config_service import AiAgentConfigService
from app.services.redis_runtime_client import get_redis_runtime_client

router = APIRouter()


async def _resolve_standard_markdown(
    session: AsyncSession,
    user_id: int,
    standard_type: str,
) -> str:
    """读取指定用户当前生效的规范内容；若用户未定制则返回系统默认完整规范。

    参数:
        session: 异步数据库会话
        user_id: 当前操作用户主键 ID
        standard_type: 规范类型 ('page' 或 'component')

    返回:
        对应的 Markdown 文本内容
    """

    try:
        service = AiAgentConfigService(session, user_id=user_id)
        configs = await service.list_code_standard_configs(AGENT_COORDINATOR_AGENT_ID)
        for item in configs:
            if item.standard_type == standard_type:
                return item.content
    except Exception:
        pass
    return get_default_code_standard(standard_type)



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
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalStandardResponse:
    """获取当前用户生效的页面开发标准 Markdown 规范。"""

    markdown = await _resolve_standard_markdown(session, auth.user.id, "page")
    return ExternalStandardResponse(
        standard_type="page",
        markdown=markdown,
    )


@router.get("/standards/component", response_model=ExternalStandardResponse)
async def get_component_standards(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("standards.component"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalStandardResponse:
    """获取当前用户生效的工作空间组件开发标准 Markdown 规范。"""

    markdown = await _resolve_standard_markdown(session, auth.user.id, "component")
    return ExternalStandardResponse(
        standard_type="component",
        markdown=markdown,
    )

