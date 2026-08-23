"""文件功能：提供 Web 控制台个人访问令牌（PAT）的创建、列表、吊销与 Scope 说明接口。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.external_operations import ALL_VALID_SCOPES, OPERATION_REGISTRY
from app.db.session import get_db_session
from app.schemas.api_access_token import (
    ApiAccessTokenCreateRequest,
    ApiAccessTokenCreateResponse,
    ApiAccessTokenListResponse,
)
from app.services.auth_service import AuthContext
from app.services.api_access_token_service import ApiAccessTokenService

router = APIRouter()


def _verify_csrf_origin(request: Request) -> None:
    """校验 Web 控制台写操作的 Origin/Referer 请求头，防止跨站请求伪造 (CSRF)。"""

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    candidate = origin or referer
    if not candidate:
        raise AppException(
            status_code=403,
            code="CSRF_CHECK_FAILED",
            detail="缺少 Origin 或 Referer 安全请求头。",
        )

    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        raise AppException(
            status_code=403,
            code="CSRF_CHECK_FAILED",
            detail="Origin 或 Referer 格式无效。",
        )

    candidate_origin = f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")

    # 允许来自请求自身精确 Host 或服务端配置中的 CORS 白名单来源 (严格包含 scheme, host, port)
    settings = get_settings()
    allowed_origins = {cors_origin.lower().rstrip("/") for cors_origin in settings.cors_origins if cors_origin}

    request_scheme = request.url.scheme.lower()
    host_header = request.headers.get("host", "").lower()
    if host_header:
        allowed_origins.add(f"{request_scheme}://{host_header}")

    if candidate_origin not in allowed_origins:
        raise AppException(
            status_code=403,
            code="CSRF_CHECK_FAILED",
            detail=f"请求来源 ({candidate_origin}) 未通过 CSRF 校验。",
        )


@router.get("", response_model=ApiAccessTokenListResponse)
async def list_access_tokens(
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiAccessTokenListResponse:
    """查询当前用户的所有个人访问令牌（脱敏显示）。"""

    return await ApiAccessTokenService(session).list_tokens(user_id=current.user.id)


@router.post("", response_model=ApiAccessTokenCreateResponse)
async def create_access_token(
    request: Request,
    response: Response,
    payload: ApiAccessTokenCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApiAccessTokenCreateResponse:
    """创建新访问令牌；明文令牌仅在本次响应中返回一次，响应严格禁止缓存。"""

    _verify_csrf_origin(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    client_ip = request.client.host if request.client else None
    return await ApiAccessTokenService(session).create_token(
        user_id=current.user.id,
        payload=payload,
        ip=client_ip,
    )


@router.post("/{token_id}/revoke")
async def revoke_access_token(
    request: Request,
    token_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    """吊销当前用户的指定访问令牌（即刻生效）。"""

    _verify_csrf_origin(request)
    client_ip = request.client.host if request.client else None
    await ApiAccessTokenService(session).revoke_token(
        user_id=current.user.id,
        token_id=token_id,
        ip=client_ip,
    )
    return {"message": "访问令牌已成功吊销"}


@router.get("/scopes")
async def list_available_scopes(
    current: Annotated[AuthContext, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """查询系统支持的所有 PAT 权限 Scope 说明及关联操作数。"""

    scope_descriptions = {
        "workspace:read": "读取工作空间基本信息与能力清单",
        "project:read": "读取项目列表、配置与结构",
        "project:write": "创建、更新与归档项目",
        "page:read": "读取页面列表、页面源码、历史版本与快照",
        "page:write": "创建、更新页面源码、执行页面变更任务与归档",
        "component:read": "读取工作空间组件列表、草稿与版本依赖",
        "component:write": "创建组件、更新组件源码、发布与归档",
        "asset:read": "读取工作空间资源列表、下载文件与文本内容",
        "asset:write": "上传资源、更新资源内容与元数据、归档与恢复",
        "design-system:read": "读取工作空间主题与样式方案列表、色板与样式配置",
        "design-system:write": "创建、复制、更新主题与样式方案、归档与恢复",
        "build:read": "读取整项目构建任务状态与构建产物",
        "build:write": "触发项目整包构建任务与生成构建快照",
    }

    result = []
    for scope in sorted(ALL_VALID_SCOPES):
        ops = [op for op, spec in OPERATION_REGISTRY.items() if scope in spec.scopes]
        result.append(
            {
                "scope": scope,
                "description": scope_descriptions.get(scope, scope),
                "operation_count": len(ops),
                "operations": ops,
            }
        )
    return result
