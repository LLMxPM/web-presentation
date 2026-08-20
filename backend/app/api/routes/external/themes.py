"""文件功能：提供 External API v1 主题管理接口（列表、详情、创建、复制、更新、归档与批量归档）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.external_api import (
    ExternalBatchArchiveRequest,
    ExternalBatchArchiveResponse,
    ExternalThemeCreateRequest,
)
from app.schemas.theme import (
    WorkspaceThemeCopyRequest,
    WorkspaceThemeCreateRequest,
    WorkspaceThemeItem,
    WorkspaceThemeUpdateRequest,
)
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService
from app.services.workspace_theme_service import WorkspaceThemeService

router = APIRouter()


@router.get("", response_model=PagedResponse[WorkspaceThemeItem])
async def list_themes(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
) -> PagedResponse[WorkspaceThemeItem]:
    """查询指定工作空间的主题列表。"""

    query = ListQuery(page=page, page_size=page_size, keyword=keyword)
    return await WorkspaceThemeService(session).list(x_workspace_id, query)


@router.get("/{theme_id}", response_model=WorkspaceThemeItem)
async def get_theme(
    theme_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
) -> WorkspaceThemeItem:
    """获取单个主题详情。"""

    return await WorkspaceThemeService(session).get(x_workspace_id, theme_id)


@router.post("", response_model=WorkspaceThemeItem)
async def create_theme(
    request: Request,
    response: Response,
    payload: ExternalThemeCreateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceThemeItem:
    """创建新主题（支持 Idempotency-Key 幂等保护）。"""

    default_palette = {
        "text": {"primary": "#0f172a", "secondary": "#64748b", "invert": "#ffffff"},
        "background": {"default": "#ffffff", "invert": "#0f172a"},
        "border": {"default": "#e2e8f0", "subtle": "#f1f5f9"},
        "link": {"default": "#2563eb", "hover": "#1d4ed8", "visited": "#7c3aed"},
        "accent": ["#2563eb", "#3b82f6"],
    }
    internal_payload = WorkspaceThemeCreateRequest(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        palette=payload.palette or default_palette,
    )

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=internal_payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceThemeItem]:
        created = await BusinessOperationService(session).create_theme(
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
        operation="theme.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, WorkspaceThemeItem) else WorkspaceThemeItem.model_validate(result)


@router.post("/{theme_id}/copy", response_model=WorkspaceThemeItem)
async def copy_theme(
    request: Request,
    theme_id: int,
    payload: WorkspaceThemeCopyRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.copy"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceThemeItem:
    """复制已有主题（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceThemeItem]:
        copied = await WorkspaceThemeService(session).copy(
            workspace_id=x_workspace_id,
            theme_id=theme_id,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 201, copied

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="theme.copy",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceThemeItem) else WorkspaceThemeItem.model_validate(result)


@router.patch("/{theme_id}", response_model=WorkspaceThemeItem)
async def update_theme(
    request: Request,
    theme_id: int,
    payload: WorkspaceThemeUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceThemeItem:
    """更新主题（禁止修改 key，支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceThemeItem]:
        updated = await BusinessOperationService(session).update_theme(
            workspace_id=x_workspace_id,
            theme_id=theme_id,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, updated

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="theme.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceThemeItem) else WorkspaceThemeItem.model_validate(result)


@router.delete("/{theme_id}")
async def archive_theme(
    request: Request,
    theme_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """归档主题（若仍被活跃项目引用则拒绝归档，支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="DELETE",
        path=request.url.path,
        json_data={"theme_id": theme_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await BusinessOperationService(session).archive_theme(
            workspace_id=x_workspace_id,
            theme_id=theme_id,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, {"message": "主题已成功归档"}

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="theme.archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, dict) else {"message": str(result)}


@router.post("/{theme_id}/restore", response_model=WorkspaceThemeItem)
async def restore_theme(
    request: Request,
    theme_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceThemeItem:
    """恢复已归档主题（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data={"theme_id": theme_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceThemeItem]:
        await BusinessOperationService(session).restore_theme(
            workspace_id=x_workspace_id,
            theme_id=theme_id,
            operator_id=auth.user.id,
            commit=False,
        )
        restored = await WorkspaceThemeService(session).get(x_workspace_id, theme_id)
        return 200, restored

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="theme.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceThemeItem) else WorkspaceThemeItem.model_validate(result)


@router.post("/batch-archive", response_model=ExternalBatchArchiveResponse)
async def batch_archive_themes(
    request: Request,
    payload: ExternalBatchArchiveRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("theme.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalBatchArchiveResponse:
    """整批原子归档多个主题。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalBatchArchiveResponse]:
        result = await BusinessOperationService(session).batch_archive_entities(
            workspace_id=x_workspace_id,
            entity_type="theme",
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
