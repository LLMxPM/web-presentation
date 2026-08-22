"""文件功能：提供 External API v1 工作空间组件管理接口（列表、详情、草稿、版本、发布、恢复、归档与批量归档）。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.external_api import (
    ExternalBatchArchiveRequest,
    ExternalBatchArchiveResponse,
    ExternalComponentMetadataUpdateRequest,
    ExternalComponentCreateMutationRequest,
    ExternalEntityValidationRequest,
    ExternalEntityValidationResponse,
    ExternalComponentApplyEditsMutationRequest,
    ExternalMutationJobResponse,
)
from app.schemas.component import (
    WorkspaceComponentItem,
    WorkspaceComponentPublishRequest,
    WorkspaceComponentVersionContent,
    WorkspaceComponentVersionListItem,
)
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService
from app.services.workspace_component_service import WorkspaceComponentService
from app.services.suggested_component_service import SuggestedComponentService
from app.services.mutation_job_service import MutationJobService
from app.api.routes.external.validate import validate_entity

router = APIRouter()


@router.post("", response_model=ExternalMutationJobResponse, status_code=202)
async def create_component(
    request: Request,
    payload: ExternalComponentCreateMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """提交组件创建 Mutation Job。"""

    await auth.ensure_workspace_access(payload.workspace_id, session)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=request.url.path, json_data=payload.model_dump(mode="json")
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job = await MutationJobService(session).enqueue_component_create_job(
            workspace_id=payload.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        return 202, await MutationJobService(session).get_job_response(job)

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=payload.workspace_id,
        idempotency_key=idempotency_key,
        operation="component.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.get("", response_model=PagedResponse[WorkspaceComponentItem])
async def list_components(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
    status: str | None = None,
    scope: str = Query(default="all", pattern="^(all|suggested)$"),
    project_id: int | None = None,
) -> PagedResponse[Any]:
    """查询指定工作空间的组件列表。"""

    if scope == "suggested":
        if project_id is None:
            raise ValueError("scope=suggested 时必须提供 project_id。")
        project_items = await SuggestedComponentService(session).list_project_component_items(
            project_id,
            workspace_id=x_workspace_id,
            include_unavailable=True,
        )
        return PagedResponse[Any](
            items=[item.model_dump(mode="json") for item in project_items],
            total=len(project_items),
            page=1,
            page_size=len(project_items) or page_size,
        )

    query = ListQuery(page=page, page_size=page_size, keyword=keyword, status=status)
    return await WorkspaceComponentService(session).list(x_workspace_id, query, user_id=auth.user.id)


@router.get("/{component_id}", response_model=WorkspaceComponentItem)
async def get_component(
    component_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentItem:
    """获取单个组件详情。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)
    return comp


@router.get("/{component_id}/dependencies")
async def get_component_dependencies(
    component_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.dependencies"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Any:
    """读取组件当前版本源码依赖。"""

    component = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(component.workspace_id, session)
    return await WorkspaceComponentService(session).get_current_dependencies(component_id, user_id=auth.user.id)


@router.post("/{component_id}/validate", response_model=ExternalEntityValidationResponse)
async def validate_component(
    component_id: int,
    payload: ExternalEntityValidationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.validate"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalEntityValidationResponse:
    """校验组件当前源码或候选内容。"""

    if payload.entity_id is not None and payload.entity_id != component_id:
        raise AppException(status_code=400, code="COMPONENT_ID_MISMATCH", detail="请求体 entity_id 必须与路径参数一致。")
    normalized = payload.model_copy(update={"entity_type": "component", "entity_id": component_id})
    return await validate_entity(normalized, auth, session)


@router.post("/{component_id}/edits", response_model=ExternalMutationJobResponse, status_code=202)
async def edit_component(
    request: Request,
    component_id: int,
    payload: ExternalComponentApplyEditsMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.edit"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """提交组件结构化源码编辑任务。"""

    component = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(component.workspace_id, session)
    if payload.component_id != component_id:
        raise AppException(status_code=400, code="COMPONENT_ID_MISMATCH", detail="请求体 component_id 必须与路径参数一致。")
    if payload.base_draft_hash is None:
        payload = payload.model_copy(update={"base_draft_hash": component.draft_hash})
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=request.url.path, json_data=payload.model_dump(mode="json")
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job = await MutationJobService(session).enqueue_component_edit_job(
            workspace_id=component.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        return 202, await MutationJobService(session).get_job_response(job)

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=component.workspace_id,
        idempotency_key=idempotency_key,
        operation="component.edit",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.patch("/{component_id}", response_model=WorkspaceComponentItem)
async def update_component_metadata(
    request: Request,
    component_id: int,
    payload: ExternalComponentMetadataUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceComponentItem:
    """仅更新组件名称或摘要，源码和结构字段继续通过 Mutation Job 写入。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)
    payload_data = payload.model_dump(mode="json", exclude_unset=True)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload_data,
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceComponentItem]:
        updated = await WorkspaceComponentService(session).update_metadata(
            component_id,
            name=payload.name,
            summary=payload.summary,
            summary_is_set="summary" in payload.model_fields_set,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, updated

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=comp.workspace_id,
        idempotency_key=idempotency_key,
        operation="component.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceComponentItem) else WorkspaceComponentItem.model_validate(result)


@router.get("/{component_id}/draft")
async def get_component_draft(
    component_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, object]:
    """读取组件当前的草稿源码与预览 Props Schema。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)
    return {
        "component_id": comp.id,
        "import_name": comp.import_name,
        "component_type": comp.component_type,
        "content": comp.content,
        "preview_schema": comp.preview_schema,
    }


@router.get("/{component_id}/versions", response_model=list[WorkspaceComponentVersionListItem])
async def list_component_versions(
    component_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WorkspaceComponentVersionListItem]:
    """查询组件的历史发布版本列表。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)
    return await WorkspaceComponentService(session).list_versions(component_id, user_id=auth.user.id)


@router.get("/{component_id}/versions/{version_no}", response_model=WorkspaceComponentVersionContent)
async def get_component_version(
    component_id: int,
    version_no: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentVersionContent:
    """读取组件指定版本的发布源码与依赖。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)
    return await WorkspaceComponentService(session).get_version_content(component_id, version_no, user_id=auth.user.id)


@router.post("/{component_id}/publish", response_model=WorkspaceComponentItem)
async def publish_component(
    request: Request,
    component_id: int,
    payload: WorkspaceComponentPublishRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.publish"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkspaceComponentItem:
    """发布组件当前草稿为新正式版本（支持 Idempotency-Key 幂等保护）。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, WorkspaceComponentItem]:
        published = await BusinessOperationService(session).publish_component(
            component_id=component_id,
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, published

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=comp.workspace_id,
        idempotency_key=idempotency_key,
        operation="component.publish",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, WorkspaceComponentItem) else WorkspaceComponentItem.model_validate(result)


@router.post("/{component_id}/archive")
async def archive_component(
    request: Request,
    component_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """归档组件（支持 Idempotency-Key 幂等保护）。"""

    comp = await WorkspaceComponentService(session).get(component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data={"component_id": component_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await WorkspaceComponentService(session).archive(component_id=component_id, user_id=auth.user.id, commit=False)
        return 200, {"message": "组件已成功归档"}

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=comp.workspace_id,
        idempotency_key=idempotency_key,
        operation="component.archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, dict) else {"message": str(result)}


@router.post("/batch-archive", response_model=ExternalBatchArchiveResponse)
async def batch_archive_components(
    request: Request,
    payload: ExternalBatchArchiveRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("component.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalBatchArchiveResponse:
    """整批原子归档多个组件。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalBatchArchiveResponse]:
        result = await BusinessOperationService(session).batch_archive_entities(
            workspace_id=x_workspace_id,
            entity_type="component",
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
