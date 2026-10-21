"""文件功能：提供 External API v1 页面管理接口（列表、详情、源码、版本历史、版本恢复、归档与批量归档）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.common import PagedResponse
from app.schemas.external_api import (
    ExternalBatchArchiveRequest,
    ExternalBatchArchiveResponse,
    ExternalErrorDetail,
    ExternalPageMetadataUpdateRequest,
    ExternalPageCopyRequest,
    ExternalPageCreateMutationRequest,
    ExternalPageApplyEditsMutationRequest,
    ExternalPageScreenshotJobCreateRequest,
    ExternalPageScreenshotJobResponse,
    ExternalPageScreenshotJobResult,
    ExternalEntityValidationRequest,
    ExternalEntityValidationResponse,
    ExternalMutationJobResponse,
)
from app.schemas.page import (
    PageCopyToProjectRequest,
    PageCurrentModuleDependencies,
    PageItem,
    PageListQuery,
    PageVersionContent,
    PageVersionListItem,
)
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService
from app.services.page_service import PageService
from app.services.page_screenshot_job_service import PageScreenshotJobService
from app.services.project_service import ProjectService
from app.services.mutation_job_service import MutationJobService
from app.api.routes.external.validate import validate_entity


router = APIRouter()


@router.post("/pages", response_model=ExternalMutationJobResponse, status_code=202)
async def create_page(
    request: Request,
    payload: ExternalPageCreateMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """创建页面并返回持久化 Mutation Job。"""

    project = await ProjectService(session).get(payload.project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=request.url.path, json_data=payload.model_dump(mode="json")
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job = await MutationJobService(session).enqueue_page_create_job(
            workspace_id=project.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        return 202, await MutationJobService(session).get_job_response(job)

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=project.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


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


@router.post("/pages/{page_id}/copy", response_model=PageItem)
async def copy_page(
    request: Request,
    response: Response,
    page_id: int,
    payload: ExternalPageCopyRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.copy"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PageItem:
    """复制页面到目标项目。"""

    source = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(source.workspace_id, session)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=request.url.path, json_data=payload.model_dump(mode="json")
    )
    copy_payload = PageCopyToProjectRequest.model_validate(payload.model_dump())

    async def _operation(record_id: int | None) -> tuple[int, PageItem]:
        copied = await PageService(session).copy_to_project(page_id, copy_payload, auth.user.id, commit=False)
        return 201, copied

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=source.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.copy",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, PageItem) else PageItem.model_validate(result)


@router.patch("/pages/{page_id}", response_model=PageItem)
async def update_page_metadata(
    request: Request,
    page_id: int,
    payload: ExternalPageMetadataUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PageItem:
    """仅更新页面轻量元数据，页面源码仍必须通过 Mutation Job 写入。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    payload_data = payload.model_dump(mode="json", exclude_unset=True)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload_data,
    )

    async def _operation(record_id: int | None) -> tuple[int, PageItem]:
        updated = await PageService(session).update_metadata(
            page_id,
            title=payload.title,
            summary=payload.summary,
            summary_is_set="summary" in payload.model_fields_set,
            speaker_notes=payload.speaker_notes,
            speaker_notes_is_set="speaker_notes" in payload.model_fields_set,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, updated

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, PageItem) else PageItem.model_validate(result)


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


@router.get("/pages/{page_id}/dependencies", response_model=PageCurrentModuleDependencies)
async def get_page_dependencies(
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.dependencies"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageCurrentModuleDependencies:
    """读取页面当前版本的源码依赖。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    return await PageService(session).get_current_module_dependencies(page_id, user_id=auth.user.id)


@router.post("/pages/{page_id}/validate", response_model=ExternalEntityValidationResponse)
async def validate_page(
    page_id: int,
    payload: ExternalEntityValidationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.validate"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalEntityValidationResponse:
    """校验页面当前源码或候选内容。"""

    if payload.entity_id is not None and payload.entity_id != page_id:
        raise AppException(status_code=400, code="PAGE_ID_MISMATCH", detail="请求体 entity_id 必须与路径参数一致。")
    normalized = payload.model_copy(update={"entity_type": "page", "entity_id": page_id})
    return await validate_entity(normalized, auth, session)


@router.post("/pages/{page_id}/edits", response_model=ExternalMutationJobResponse, status_code=202)
async def edit_page(
    request: Request,
    page_id: int,
    payload: ExternalPageApplyEditsMutationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.edit"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalMutationJobResponse:
    """提交页面结构化源码编辑任务。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    if payload.page_id != page_id:
        raise AppException(status_code=400, code="PAGE_ID_MISMATCH", detail="请求体 page_id 必须与路径参数一致。")
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=request.url.path, json_data=payload.model_dump(mode="json")
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalMutationJobResponse]:
        job = await MutationJobService(session).enqueue_page_edit_job(
            workspace_id=page.workspace_id,
            user_id=auth.user.id,
            payload=payload,
            idempotency_record_id=record_id,
        )
        return 202, await MutationJobService(session).get_job_response(job)

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.edit",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalMutationJobResponse) else ExternalMutationJobResponse.model_validate(result)


@router.get(
    "/pages/{page_id}/screenshot",
    response_class=Response,
    responses={200: {
        "description": "最新页面 PNG；可能等待持久队列刷新截图。",
        "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
        "headers": {
            "X-Page-ID": {"description": "页面 ID", "schema": {"type": "integer"}},
            "X-Page-Version-No": {"description": "截图对应页面版本", "schema": {"type": "integer"}},
        },
    }},
)
async def get_page_screenshot(
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.screenshot.latest"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """获取指定页面的最新 PNG 截图。"""

    page = await PageService(session)._get_page_or_raise(page_id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    await PageService(session)._ensure_page_access(page, user_id=auth.user.id)

    screenshot_result = await PageScreenshotJobService(session).ensure_latest_page_screenshot_via_queue(
        page_id=page_id,
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        project_id=page.project_id,
    )
    version_no = screenshot_result.page.screenshot_version_no or screenshot_result.page.current_version_no or 1
    return Response(
        content=screenshot_result.content,
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache",
            "X-Page-ID": str(page.id),
            "X-Page-Version-No": str(version_no),
        },
    )


@router.post(
    "/pages/{page_id}/screenshot-jobs",
    response_model=ExternalPageScreenshotJobResponse,
    status_code=202,
)
async def create_page_screenshot_job_external(
    request: Request,
    page_id: int,
    payload: ExternalPageScreenshotJobCreateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.screenshot.job.create"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalPageScreenshotJobResponse:
    """提交页面截图任务；提供 motion_snapshot 时只返回临时帧，不更新默认截图。"""

    page = await PageService(session)._get_page_or_raise(page_id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    await PageService(session)._ensure_page_access(page, user_id=auth.user.id)
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST", path=request.url.path, json_data=payload.model_dump(mode="json")
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalPageScreenshotJobResponse]:
        job = await PageScreenshotJobService(session).create_page_screenshot_job(
            page_id=page_id,
            current=auth,
            viewport_width=payload.viewport_width,
            viewport_height=payload.viewport_height,
            target_page_version_no=payload.target_page_version_no,
            motion_snapshot=payload.motion_snapshot,
            source="external",
            commit=False,
        )
        return 202, _external_screenshot_job_response(job)

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=page.workspace_id,
        idempotency_key=idempotency_key,
        operation="page.screenshot.job.create",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalPageScreenshotJobResponse) else ExternalPageScreenshotJobResponse.model_validate(result)


@router.get(
    "/pages/{page_id}/screenshot-jobs/{job_id}",
    response_model=ExternalPageScreenshotJobResponse,
)
async def get_page_screenshot_job_external(
    page_id: int,
    job_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.screenshot.job.status"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalPageScreenshotJobResponse:
    """查询指定页面的截图任务状态；任务必须属于路径中的页面。"""

    page = await PageService(session)._get_page_or_raise(page_id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    await PageService(session)._ensure_page_access(page, user_id=auth.user.id)
    job = await PageScreenshotJobService(session).get_job_by_id(job_id)
    if int(job.page_id) != int(page_id) or int(job.workspace_id or 0) != int(page.workspace_id or 0):
        raise AppException(status_code=404, code="PAGE_SCREENSHOT_JOB_NOT_FOUND", detail="截图任务不存在。")
    return _external_screenshot_job_response(job)


@router.get(
    "/pages/{page_id}/screenshot-jobs/{job_id}/content",
    summary="External API 读取页面截图任务内容",
    response_class=Response,
    responses={200: {
        "description": "任务成功后的页面 PNG；未成功返回 409。",
        "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
        "headers": {
            "X-Page-ID": {"description": "页面 ID", "schema": {"type": "integer"}},
            "X-Page-Version-No": {"description": "截图对应页面版本", "schema": {"type": "integer"}},
            "X-Screenshot-Id": {"description": "截图内容 SHA-256", "schema": {"type": "string"}},
        },
    }},
)
@router.head(
    "/pages/{page_id}/screenshot-jobs/{job_id}/content",
    include_in_schema=False,
)
async def get_page_screenshot_job_content_external(
    page_id: int,
    job_id: int,
    request: Request,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.screenshot.job.content"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    download: int = 0,
):
    """读取已成功任务对应的 PNG；未成功时返回 409，不回退默认最新截图。"""

    from app.services.file_auth_service import FileAuthService
    from app.services.object_storage_service import ObjectStorageService

    page = await PageService(session).get_model(page_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(page.workspace_id, session)
    job = await PageScreenshotJobService(session).get_job_by_id(job_id)
    if int(job.page_id) != int(page_id) or int(job.workspace_id or 0) != int(page.workspace_id or 0):
        raise AppException(status_code=404, code="PAGE_SCREENSHOT_JOB_NOT_FOUND", detail="截图任务不存在。")
    if job.status != "succeeded" or not job.result_storage_key or not job.result_sha256:
        raise AppException(
            status_code=409,
            code="PAGE_SCREENSHOT_JOB_NOT_READY",
            detail="截图任务尚未成功完成，请等待任务终态后重试。",
        )
    name = f"page-{page.id}-{job.result_sha256[:8]}.png"
    response = await FileAuthService.serve_protected_file(
        request=request,
        open_file=ObjectStorageService().open_object_for_read(
            job.result_storage_key, expected_sha256=job.result_sha256
        ),
        etag=job.result_sha256,
        media_type="image/png",
        original_name=name,
        is_download=download == 1,
    )
    response.headers["X-Page-ID"] = str(page.id)
    response.headers["X-Page-Version-No"] = str(job.target_page_version_no)
    response.headers["X-Screenshot-Id"] = job.result_sha256
    return response


def _external_screenshot_job_response(job) -> ExternalPageScreenshotJobResponse:
    """把内部 ORM/响应模型收敛为外部 DTO；结果只暴露内容地址、版本与有界采样摘要。"""

    job_id = int(getattr(job, "job_id", None) or getattr(job, "id"))
    result_sha256 = getattr(job, "result_sha256", None) or getattr(job, "result_screenshot_id", None)
    applied_motion = getattr(job, "result_applied_motion_json", None) or getattr(job, "applied_motion", None)
    motion_snapshot = getattr(job, "motion_snapshot_json", None) or getattr(job, "motion_snapshot", None)
    page_id = int(job.page_id)
    result = None
    if job.status == "succeeded" and result_sha256:
        result = ExternalPageScreenshotJobResult(
            screenshot_id=result_sha256,
            content_url=f"/api/v1/pages/{page_id}/screenshot-jobs/{job_id}/content",
            version_no=job.target_page_version_no,
            width=job.viewport_width,
            height=job.viewport_height,
            applied_motion=applied_motion,
        )
    return ExternalPageScreenshotJobResponse(
        job_id=job_id,
        page_id=page_id,
        workspace_id=job.workspace_id,
        status=job.status,
        motion_snapshot=motion_snapshot,
        result=result,
        error=(
            ExternalErrorDetail(code=job.error_code, message=job.error_message or "页面截图任务失败。")
            if job.error_code
            else None
        ),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        cancel_requested_at=job.cancel_requested_at,
    )



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


@router.post("/pages/{page_id}/archive")
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
        http_method="POST",
        path=request.url.path,
        json_data={"page_id": page_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await BusinessOperationService(session).archive_page(page_id=page_id, operator_id=auth.user.id, commit=False)
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


@router.get(
    "/pages/{page_id}/screenshots/{screenshot_id}/content",
    summary="External API 读取页面截图",
)
@router.head(
    "/pages/{page_id}/screenshots/{screenshot_id}/content",
    include_in_schema=False,
)
async def get_external_page_screenshot_content(
    page_id: int,
    screenshot_id: str,
    request: Request,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.screenshot.content"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    download: int = 0,
):
    """External API 读取页面已生成的截图产物。"""

    from app.services.screenshot_artifact_service import serve_screenshot

    page = await PageService(session).get_model(page_id, user_id=auth.user.id)
    if page.workspace_id is not None and page.workspace_id != x_workspace_id:
        raise AppException(
            status_code=404,
            code="PAGE_NOT_FOUND",
            detail="页面不存在或不属于当前工作空间。",
            headers={"Cache-Control": "no-store"},
        )
    await auth.ensure_workspace_access(x_workspace_id, session)
    return await serve_screenshot(request, page, screenshot_id, download=download == 1)
