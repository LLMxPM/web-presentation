"""文件功能：提供项目整包构建任务的创建与查询接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.project_build import ProjectBuildCreateRequest, ProjectBuildJobResponse
from app.services.auth_service import AuthContext
from app.services.object_storage_service import ObjectStorageService
from app.services.project_build_service import ProjectBuildService, run_project_build_job
from app.services.project_service import ProjectService

router = APIRouter()


@router.post("/projects/{project_id}/build-jobs", response_model=ProjectBuildJobResponse)
async def create_project_build_job(
    project_id: int,
    payload: ProjectBuildCreateRequest,
    background_tasks: BackgroundTasks,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectBuildJobResponse:
    """创建项目整包构建任务，并异步派发给 Runtime。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    service = ProjectBuildService(session)
    job = await service.create_build_job(project_id=project_id, payload=payload, created_by=current.user.id)
    background_tasks.add_task(run_project_build_job, job.id)
    return ProjectBuildJobResponse.model_validate(job)


@router.get("/projects/{project_id}/build-jobs/latest", response_model=ProjectBuildJobResponse | None)
async def get_latest_project_build_job(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectBuildJobResponse | None:
    """读取项目最近一次构建任务。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    job = await ProjectBuildService(session).get_latest_job(project_id)
    if job is None:
        return None
    return ProjectBuildJobResponse.model_validate(job)


@router.get("/projects/{project_id}/build-jobs", response_model=list[ProjectBuildJobResponse])
async def list_project_build_jobs(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=20, ge=1, le=50),
) -> list[ProjectBuildJobResponse]:
    """读取项目最近的构建历史。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    jobs = await ProjectBuildService(session).list_jobs(project_id, limit=limit)
    return [ProjectBuildJobResponse.model_validate(job) for job in jobs]


@router.get("/build-jobs/{job_id}", response_model=ProjectBuildJobResponse)
async def get_project_build_job(
    job_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectBuildJobResponse:
    """按任务 ID 查询构建状态。"""

    job = await ProjectBuildService(session).get_job_by_id(job_id)
    await ProjectService(session).get(job.project_id, user_id=current.user.id)
    return ProjectBuildJobResponse.model_validate(job)


@router.get("/projects/{project_id}/build-jobs/{job_id}/artifact")
async def download_project_build_artifact(
    project_id: int,
    job_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """下载指定项目构建任务的归档产物。"""

    service = ProjectBuildService(session)
    job = await service.get_job_by_project_and_id(project_id, job_id)
    await ProjectService(session).get(job.project_id, user_id=current.user.id)
    if not job.artifact_storage_key:
        raise AppException(status_code=404, code="BUILD_ARTIFACT_NOT_FOUND", detail="当前构建任务尚未生成可下载产物。")
    content = await ObjectStorageService().read_object(job.artifact_storage_key)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="project-{project_id}-build-{job_id}.zip"'},
    )
