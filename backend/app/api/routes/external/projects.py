"""文件功能：提供 External API v1 项目管理接口（列表、详情、创建、更新、归档与批量归档）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.external_api import (
    ExternalBatchArchiveRequest,
    ExternalBatchArchiveResponse,
    ExternalProjectCreateRequest,
)
from app.schemas.project import ProjectCreateRequest, ProjectItem, ProjectUpdateRequest
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService
from app.services.project_service import ProjectService

router = APIRouter()


@router.get("", response_model=PagedResponse[ProjectItem])
async def list_projects(
    request: Request,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    status: str | None = None,
) -> PagedResponse[ProjectItem]:
    """查询指定工作空间的项目列表。"""

    query = ListQuery(page=page, page_size=page_size, keyword=keyword, status=status)
    return await ProjectService(session).list(query=query, workspace_id=x_workspace_id, user_id=auth.user.id)


@router.get("/{project_id}", response_model=ProjectItem)
async def get_project(
    project_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectItem:
    """获取单个项目详情。"""

    project = await ProjectService(session).get(project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)
    return project


@router.post("", response_model=ProjectItem)
async def create_project(
    request: Request,
    response: Response,
    payload: ExternalProjectCreateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ProjectItem:
    """创建新项目（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    internal_payload = ProjectCreateRequest(
        workspace_id=x_workspace_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        configuration=payload.configuration or {},
        build_extra_assets_json=payload.build_extra_assets_json or {},
    )

    async def _operation(record_id: int | None) -> tuple[int, ProjectItem]:
        created = await BusinessOperationService(session).create_project(
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
        operation="project.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, ProjectItem) else ProjectItem.model_validate(result)


@router.patch("/{project_id}", response_model=ProjectItem)
async def update_project(
    request: Request,
    project_id: int,
    payload: ProjectUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ProjectItem:
    """更新项目基础属性（支持 Idempotency-Key 幂等保护）。"""

    project = await ProjectService(session).get(project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)
    if payload.workspace_id is not None and payload.workspace_id != project.workspace_id:
        raise AppException(
            status_code=400,
            code="PROJECT_WORKSPACE_MOVE_FORBIDDEN",
            detail="External API 不支持修改项目所属工作空间。",
        )

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ProjectItem]:
        updated = await BusinessOperationService(session).update_project(
            project_id=project_id,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, updated

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=project.workspace_id,
        idempotency_key=idempotency_key,
        operation="project.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ProjectItem) else ProjectItem.model_validate(result)


@router.delete("/{project_id}")
async def archive_project(
    request: Request,
    project_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """归档项目（支持 Idempotency-Key 幂等保护）。"""

    project = await ProjectService(session).get(project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="DELETE",
        path=request.url.path,
        json_data={"project_id": project_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await BusinessOperationService(session).archive_project(
            project_id=project_id,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, {"message": "项目已成功归档"}

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=project.workspace_id,
        idempotency_key=idempotency_key,
        operation="project.archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, dict) else {"message": str(result)}


@router.post("/batch-archive", response_model=ExternalBatchArchiveResponse)
async def batch_archive_projects(
    request: Request,
    payload: ExternalBatchArchiveRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalBatchArchiveResponse:
    """整批原子归档多个项目。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalBatchArchiveResponse]:
        result = await BusinessOperationService(session).batch_archive_entities(
            workspace_id=x_workspace_id,
            entity_type="project",
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
