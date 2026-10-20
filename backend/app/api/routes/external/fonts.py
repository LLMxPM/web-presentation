"""文件功能：提供 External API v1 字体与字体族管理接口（列表、详情、注册、配置更新与族重命名）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.external_api import (
    ExternalFontRegisterRequest,
    ExternalFontUpdateRequest,
)
from app.schemas.font import (
    WorkspaceFontConfigCreateRequest,
    WorkspaceFontConfigResponse,
    WorkspaceFontConfigUpdateRequest,
    WorkspaceFontFamilyResponse,
    WorkspaceFontFamilyUpdateRequest,
)
from app.services.idempotency_service import IdempotencyService
from app.services.workspace_font_service import WorkspaceFontService

router = APIRouter()


@router.get("/fonts", response_model=PagedResponse[WorkspaceFontConfigResponse])
async def list_fonts(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
) -> PagedResponse[WorkspaceFontConfigResponse]:
    """查询工作空间注册的字体 face 列表。"""
    query = ListQuery(page=page, page_size=page_size, keyword=keyword)
    return await WorkspaceFontService(session).list_workspace_fonts(x_workspace_id, query)


@router.get("/fonts/{font_id}", response_model=WorkspaceFontConfigResponse)
async def get_font(
    font_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
) -> WorkspaceFontConfigResponse:
    """获取单个字体 face 配置详情。"""
    return await WorkspaceFontService(session).get_workspace_font(x_workspace_id, font_id)


@router.post("/fonts", response_model=WorkspaceFontConfigResponse)
async def register_font(
    request: Request,
    response: Response,
    payload: ExternalFontRegisterRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font.register"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceFontConfigResponse:
    """对已上传的字体资源注册 face（支持 Idempotency-Key 幂等保护）。"""
    internal_payload = WorkspaceFontConfigCreateRequest(
        asset_id=payload.asset_id,
        family_name=payload.family_name,
        font_format=payload.font_format,
        font_weight=payload.font_weight,
        font_style=payload.font_style,
        font_display=payload.font_display,
    )

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceFontConfigResponse]:
        created = await WorkspaceFontService(session).create_workspace_font(
            workspace_id=x_workspace_id,
            payload=internal_payload,
            commit=False,
        )
        return 201, created

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="font.register",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, WorkspaceFontConfigResponse) else WorkspaceFontConfigResponse.model_validate(result)


@router.patch("/fonts/{font_id}", response_model=WorkspaceFontConfigResponse)
async def update_font(
    request: Request,
    font_id: int,
    payload: ExternalFontUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceFontConfigResponse:
    """更新字体 face 配置或移动所属族（支持 Idempotency-Key 幂等保护）。"""
    internal_payload = WorkspaceFontConfigUpdateRequest(
        family_name=payload.family_name,
        font_format=payload.font_format,
        font_weight=payload.font_weight,
        font_style=payload.font_style,
        font_display=payload.font_display,
    )

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload.model_dump(mode="json", exclude_unset=True),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceFontConfigResponse]:
        updated = await WorkspaceFontService(session).update_workspace_font(
            workspace_id=x_workspace_id,
            font_id=font_id,
            payload=internal_payload,
            commit=False,
        )
        return 200, updated

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="font.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceFontConfigResponse) else WorkspaceFontConfigResponse.model_validate(result)


@router.get("/font-families", response_model=PagedResponse[WorkspaceFontFamilyResponse])
async def list_font_families(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font_family.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
) -> PagedResponse[WorkspaceFontFamilyResponse]:
    """查询工作空间字体族列表及各族包含的 faces 摘要。"""
    query = ListQuery(page=page, page_size=page_size, keyword=keyword)
    return await WorkspaceFontService(session).list_workspace_font_families(x_workspace_id, query)


@router.get("/font-families/{family_id}", response_model=WorkspaceFontFamilyResponse)
async def get_font_family(
    family_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font_family.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
) -> WorkspaceFontFamilyResponse:
    """获取单个字体族详情及包含的全部 faces。"""
    return await WorkspaceFontService(session).get_workspace_font_family(x_workspace_id, family_id)


@router.patch("/font-families/{family_id}", response_model=WorkspaceFontFamilyResponse)
async def rename_font_family(
    request: Request,
    family_id: int,
    payload: WorkspaceFontFamilyUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font_family.rename"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceFontFamilyResponse:
    """重命名字体族并级联同步相关主题字体标签（支持 Idempotency-Key 幂等保护）。"""
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceFontFamilyResponse]:
        renamed = await WorkspaceFontService(session).rename_font_family(
            workspace_id=x_workspace_id,
            family_id=family_id,
            payload=payload,
            commit=False,
        )
        return 200, renamed

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="font_family.rename",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceFontFamilyResponse) else WorkspaceFontFamilyResponse.model_validate(result)
