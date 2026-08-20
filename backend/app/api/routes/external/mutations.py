"""文件功能：提供 External API v1 异步 Mutation 任务的创建、状态查询与取消接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import (
    ExternalAuthContext,
    require_dynamic_mutation_operation,
    require_external_operation,
)
from app.db.session import get_db_session
from app.models.api_mutation_job import ApiMutationJob
from app.schemas.external_api import (
    ExternalComponentApplyEditsMutationRequest,
    ExternalComponentCreateMutationRequest,
    ExternalMutationJobResponse,
    ExternalPageApplyEditsMutationRequest,
    ExternalPageCreateMutationRequest,
)
from app.services.idempotency_service import IdempotencyService
from app.services.mutation_job_service import MutationJobService
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService

router = APIRouter()


@router.post("/pages", response_model=ExternalMutationJobResponse)
async def create_page_mutation(
    request: Request,
    response: Response,
    payload: ExternalPageCreateMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("jobs.mutation.page.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """入队页面创建异步 Mutation 任务（慢 AST 与 Chromium 诊断由后台 Worker 执行，支持 Idempotency-Key 幂等保护）。"""

    project = await ProjectService(session).get(payload.project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job_service = MutationJobService(session)
        job = await job_service.enqueue_page_create_job(
            workspace_id=project.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        resp = await job_service.get_job_response(job)
        return 202, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=project.workspace_id,
        idempotency_key=idempotency_key,
        operation="jobs.mutation.page.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.post("/pages/edits", response_model=ExternalMutationJobResponse)
async def create_page_edits_mutation(
    request: Request,
    response: Response,
    payload: ExternalPageApplyEditsMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("jobs.mutation.page.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """入队页面结构化编辑异步 Mutation 任务（支持 Idempotency-Key 幂等保护）。"""

    page = await PageService(session).get(payload.page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job_service = MutationJobService(session)
        job = await job_service.enqueue_page_edit_job(
            workspace_id=page.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        resp = await job_service.get_job_response(job)
        return 202, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        idempotency_key=idempotency_key,
        operation="jobs.mutation.page.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.post("/components", response_model=ExternalMutationJobResponse)
async def create_component_mutation(
    request: Request,
    response: Response,
    payload: ExternalComponentCreateMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("jobs.mutation.component.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """入队组件创建异步 Mutation 任务（支持 Idempotency-Key 幂等保护）。"""

    await auth.ensure_workspace_access(payload.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job_service = MutationJobService(session)
        job = await job_service.enqueue_component_create_job(
            workspace_id=payload.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        resp = await job_service.get_job_response(job)
        return 202, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=payload.workspace_id,
        idempotency_key=idempotency_key,
        operation="jobs.mutation.component.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.post("/components/edits", response_model=ExternalMutationJobResponse)
async def create_component_edits_mutation(
    request: Request,
    response: Response,
    payload: ExternalComponentApplyEditsMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("jobs.mutation.component.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """入队组件结构化编辑异步 Mutation 任务（支持 Idempotency-Key 幂等保护）。"""

    comp = await WorkspaceComponentService(session).get(payload.component_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(comp.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )
    if payload.base_draft_hash is None:
        payload = payload.model_copy(update={"base_draft_hash": comp.draft_hash})

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job_service = MutationJobService(session)
        job = await job_service.enqueue_component_edit_job(
            workspace_id=comp.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        resp = await job_service.get_job_response(job)
        return 202, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=comp.workspace_id,
        idempotency_key=idempotency_key,
        operation="jobs.mutation.component.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.get("/{job_id}", response_model=ExternalMutationJobResponse)
async def get_mutation_job_status(
    context_and_job: Annotated[tuple[ExternalAuthContext, ApiMutationJob], Depends(require_dynamic_mutation_operation("status"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalMutationJobResponse:
    """查询异步 Mutation 任务的状态与结果（动态 Scope 鉴权）。"""

    _, job = context_and_job
    return await MutationJobService(session).get_job_response(job)


@router.post("/{job_id}/cancel", response_model=ExternalMutationJobResponse)
async def cancel_mutation_job(
    context_and_job: Annotated[tuple[ExternalAuthContext, ApiMutationJob], Depends(require_dynamic_mutation_operation("cancel"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalMutationJobResponse:
    """请求取消异步 Mutation 任务（动态 Scope 鉴权）。"""

    _, job = context_and_job
    return await MutationJobService(session).request_cancel_job(job)
