"""文件功能：提供 External API v1 项目与页面预览地址接口，并复用统一 PreviewService。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.external_api import ExternalPreviewArtifactCreateRequest
from app.schemas.release import PreviewArtifactResponse, PreviewEntryDescriptor
from app.services.page_service import PageService
from app.services.preview_service import PreviewService
from app.services.project_service import ProjectService

router = APIRouter()


async def _create_external_preview_artifact(
    *,
    auth: ExternalAuthContext,
    session: AsyncSession,
    project_id: int,
    workspace_id: int,
    entry_descriptor: PreviewEntryDescriptor | None,
) -> PreviewArtifactResponse:
    """执行项目/页面预览共有的权限确认与 artifact 创建流程。"""

    await auth.ensure_workspace_access(workspace_id, session)
    return await PreviewService(session).create_preview_artifact(
        project_id=project_id,
        entry_descriptor=entry_descriptor,
        tenant_id=f"tenant_{auth.user.id}",
    )


@router.post(
    "/projects/{project_id}/preview-artifact",
    response_model=PreviewArtifactResponse,
    response_model_exclude_none=True,
)
async def create_project_preview_artifact(
    project_id: int,
    payload: ExternalPreviewArtifactCreateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("project.preview"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """创建整项目预览 artifact，并返回短期预览地址。"""

    project = await ProjectService(session).get(project_id, user_id=auth.user.id)
    entry_descriptor = (
        PreviewEntryDescriptor(entry_type="route", route=payload.route) if payload.route is not None else None
    )
    return await _create_external_preview_artifact(
        auth=auth,
        session=session,
        project_id=project.id,
        workspace_id=project.workspace_id,
        entry_descriptor=entry_descriptor,
    )


@router.post(
    "/pages/{page_id}/preview-artifact",
    response_model=PreviewArtifactResponse,
    response_model_exclude_none=True,
)
async def create_page_preview_artifact(
    page_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("page.preview"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """创建单页面预览 artifact，并由 Backend 解析页面模块入口。"""

    page = await PageService(session).get(page_id, user_id=auth.user.id)
    if page.project_id is None or page.workspace_id is None:
        raise AppException(
            status_code=409,
            code="PAGE_PROJECT_REQUIRED",
            detail="页面必须归属于项目后才能创建预览地址。",
        )
    entry_descriptor = PreviewEntryDescriptor(
        entry_type="module",
        module_path=f"src/views/{page.code}.{page.file_type.value}",
    )
    return await _create_external_preview_artifact(
        auth=auth,
        session=session,
        project_id=page.project_id,
        workspace_id=page.workspace_id,
        entry_descriptor=entry_descriptor,
    )
