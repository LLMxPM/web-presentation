"""文件功能：提供 External API v1 样式方案管理接口（列表、详情、创建、复制、更新、归档与批量归档）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.external_api import (
    ExternalBatchArchiveRequest,
    ExternalBatchArchiveResponse,
    ExternalStyleCreateRequest,
)
from app.schemas.workspace_style import (
    WorkspaceStyleCopyRequest,
    WorkspaceStyleCreateRequest,
    WorkspaceStyleItem,
    WorkspaceStyleUpdateRequest,
)
from app.schemas.presentation_style import StyleConfiguration
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService
from app.services.workspace_style_service import WorkspaceStyleService

router = APIRouter()


@router.get("", response_model=PagedResponse[WorkspaceStyleItem])
async def list_styles(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
) -> PagedResponse[WorkspaceStyleItem]:
    """查询指定工作空间的样式列表。"""

    query = ListQuery(page=page, page_size=page_size, keyword=keyword)
    return await WorkspaceStyleService(session).list(x_workspace_id, query)


@router.get("/{style_id}", response_model=WorkspaceStyleItem)
async def get_style(
    style_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
) -> WorkspaceStyleItem:
    """获取单个样式方案详情。"""

    return await WorkspaceStyleService(session).get(x_workspace_id, style_id)


@router.post("", response_model=WorkspaceStyleItem)
async def create_style(
    request: Request,
    response: Response,
    payload: ExternalStyleCreateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceStyleItem:
    """创建新样式方案（支持 Idempotency-Key 幂等保护）。"""

    style_key = payload.key or f"style-{uuid.uuid4().hex[:8]}"
    internal_payload = WorkspaceStyleCreateRequest(
        name=payload.name,
        key=style_key,
        description=payload.description,
        configuration=StyleConfiguration.model_validate(payload.configuration),
    )

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceStyleItem]:
        created = await BusinessOperationService(session).create_style(
            workspace_id=x_workspace_id,
            payload=internal_payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 201, created

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="style.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, WorkspaceStyleItem) else WorkspaceStyleItem.model_validate(result)


@router.post("/{style_id}/copy", response_model=WorkspaceStyleItem)
async def copy_style(
    request: Request,
    response: Response,
    style_id: int,
    payload: WorkspaceStyleCopyRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.copy"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceStyleItem:
    """复制已有样式方案（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceStyleItem]:
        copied = await WorkspaceStyleService(session).copy(
            workspace_id=x_workspace_id,
            style_id=style_id,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 201, copied

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="style.copy",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, WorkspaceStyleItem) else WorkspaceStyleItem.model_validate(result)


@router.patch("/{style_id}", response_model=WorkspaceStyleItem)
async def update_style(
    request: Request,
    style_id: int,
    payload: WorkspaceStyleUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceStyleItem:
    """更新样式方案（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceStyleItem]:
        updated = await BusinessOperationService(session).update_style(
            workspace_id=x_workspace_id,
            style_id=style_id,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, updated

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="style.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceStyleItem) else WorkspaceStyleItem.model_validate(result)


@router.post("/{style_id}/archive")
async def archive_style(
    request: Request,
    style_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """归档样式方案（默认方案受保护禁止归档，支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data={"style_id": style_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await BusinessOperationService(session).archive_style(
            workspace_id=x_workspace_id,
            style_id=style_id,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, {"message": "样式方案已成功归档"}

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="style.archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, dict) else {"message": str(result)}


@router.post("/batch-archive", response_model=ExternalBatchArchiveResponse)
async def batch_archive_styles(
    request: Request,
    payload: ExternalBatchArchiveRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("style.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalBatchArchiveResponse:
    """整批原子归档多个样式方案。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalBatchArchiveResponse]:
        result = await BusinessOperationService(session).batch_archive_entities(
            workspace_id=x_workspace_id,
            entity_type="style",
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, result

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="operations.batch_archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalBatchArchiveResponse) else ExternalBatchArchiveResponse.model_validate(result)
