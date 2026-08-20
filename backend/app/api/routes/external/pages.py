"""文件功能：提供 External API v1 页面管理接口（列表、详情、源码、版本历史、版本恢复、归档与批量归档）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.common import PagedResponse
from app.schemas.external_api import ExternalBatchArchiveRequest, ExternalBatchArchiveResponse
from app.schemas.page import (
    PageItem,
    PageListQuery,
    PageVersionContent,
    PageVersionListItem,
    PageVersionRestoreRequest,
)
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService
from app.services.page_service import PageService

from app.services.project_service import ProjectService

router = APIRouter()


@router.get("/projects/{project_id}/pages", response_model=PagedResponse[PageItem])
async def list_project_pages(
    project_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
    status: str | None = None,
) -> PagedResponse[PageItem]:
    """查询指定项目下的所有页面。"""

    project = await ProjectService(session).get(project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)

    query = PageListQuery(page=page, page_size=page_size, keyword=keyword, status=status, project_id=project_id)
    return await PageService(session).list(query, user_id=auth.user.id)


@router.get("/pages/{page_id}", response_model=PageItem)
async def get_page(
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """获取指定页面的元数据详情。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    return page


@router.get("/pages/{page_id}/source")
async def get_page_source(
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, object]:
    """读取页面的当前最新 Vue 源码。"""

    page = await PageService(session)._get_page_or_raise(page_id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    await PageService(session)._ensure_page_access(page, user_id=auth.user.id)
    return {
        "page_id": page.id,
        "page_code": page.code,
        "version_no": page.current_version_no,
        "source_code": page.page_content,
    }


@router.get("/pages/{page_id}/versions", response_model=list[PageVersionListItem])
async def list_page_versions(
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[PageVersionListItem]:
    """查询页面的历史版本列表。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    return await PageService(session).list_versions(page_id, user_id=auth.user.id)


@router.get("/pages/{page_id}/versions/{version_no}", response_model=PageVersionContent)
async def get_page_version(
    page_id: int,
    version_no: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageVersionContent:
    """获取指定页面版本的完整源码与元数据。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    return await PageService(session).get_version_content(page_id, version_no, user_id=auth.user.id)


@router.post("/pages/{page_id}/versions/{version_no}/restore", response_model=PageItem)
async def restore_page_version(
    request: Request,
    page_id: int,
    version_no: int,
    payload: PageVersionRestoreRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PageItem:
    """将指定历史版本恢复为最新版本（支持 Idempotency-Key 幂等保护）。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, PageItem]:
        restored = await PageService(session).restore_version(
            page_id=page_id,
            version_no=version_no,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, restored

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, PageItem) else PageItem.model_validate(result)


@router.delete("/pages/{page_id}")
async def archive_page(
    request: Request,
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """归档单项页面（支持 Idempotency-Key 幂等保护）。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="DELETE",
        path=request.url.path,
        json_data={"page_id": page_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await PageService(session).delete(page_id=page_id, user_id=auth.user.id, commit=False)
        return 200, {"message": "页面已成功归档"}

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, dict) else {"message": str(result)}


@router.post("/pages/batch-archive", response_model=ExternalBatchArchiveResponse)
async def batch_archive_pages(
    request: Request,
    payload: ExternalBatchArchiveRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalBatchArchiveResponse:
    """整批原子归档多个页面。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalBatchArchiveResponse]:
        result = await BusinessOperationService(session).batch_archive_entities(
            workspace_id=x_workspace_id,
            entity_type="page",
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
