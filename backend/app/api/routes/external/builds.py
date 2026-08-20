"""文件功能：提供 External API v1 项目整包构建任务触发与状态查询接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.project_build import ProjectBuildCreateRequest, ProjectBuildJobResponse
from app.services.idempotency_service import IdempotencyService
from app.services.project_build_service import ProjectBuildService
from app.services.project_service import ProjectService

router = APIRouter()


@router.post("/projects/{project_id}/builds", response_model=ProjectBuildJobResponse)
async def trigger_project_build(
    request: Request,
    response: Response,
    project_id: int,
    payload: ProjectBuildCreateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("jobs.build.start"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ProjectBuildJobResponse:
    """触发项目整包构建任务（支持 Idempotency-Key 幂等保护）。"""

    project = await ProjectService(session).get(project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ProjectBuildJobResponse]:
        build_job = await ProjectBuildService(session).create_build_job(
            project_id=project_id,
            payload=payload,
            created_by=auth.user.id,
            commit=False,
        )
        resp = ProjectBuildJobResponse.model_validate(build_job)
        return 201, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=project.workspace_id,
        idempotency_key=idempotency_key,
        operation="jobs.build.start",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, ProjectBuildJobResponse) else ProjectBuildJobResponse.model_validate(result)


@router.get("/builds/{job_id}", response_model=ProjectBuildJobResponse)
async def get_build_job_status(
    job_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("jobs.build.status"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectBuildJobResponse:
    """查询项目构建任务状态与产物下载链接。"""

    job = await ProjectBuildService(session).get_build_job(job_id)
    project = await ProjectService(session).get(job.project_id, user_id=auth.user.id)
    await auth.ensure_workspace_access(project.workspace_id, session)
    return ProjectBuildJobResponse.model_validate(job)
