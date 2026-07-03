"""文件功能：提供项目模板包导出、导入预检、正式导入和临时预览接口。"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.schemas.project_template import (
    ProjectTemplateExportRequest,
    ProjectTemplateExportValidationResult,
    ProjectTemplateImportResult,
    ProjectTemplateImportValidationResult,
)
from app.schemas.release import PreviewArtifactResponse
from app.services.auth_service import AuthContext
from app.services.project_service import ProjectService
from app.services.project_template_package_service import ProjectTemplatePackageService
from app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.post(
    "/projects/{project_id}/template-package/export/validate",
    response_model=ProjectTemplateExportValidationResult,
)
async def validate_project_template_package_export(
    project_id: int,
    payload: ProjectTemplateExportRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectTemplateExportValidationResult:
    """预检项目模板包导出内容，不生成 ZIP。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    return await ProjectTemplatePackageService(session).validate_export_package(
        project_id=project_id,
        payload=payload,
    )


@router.post("/projects/{project_id}/template-package/export")
async def export_project_template_package(
    project_id: int,
    payload: ProjectTemplateExportRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """导出项目模板包 ZIP。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    archive_content, filename = await ProjectTemplatePackageService(session).export_package(
        project_id=project_id,
        payload=payload,
        current_user_id=current.user.id,
        current_user_display_name=current.user.display_name,
    )
    return Response(
        content=archive_content,
        media_type="application/zip",
        headers={"Content-Disposition": build_template_package_content_disposition(filename)},
    )


@router.post(
    "/workspaces/{workspace_id}/template-packages/import/validate",
    response_model=ProjectTemplateImportValidationResult,
)
async def validate_project_template_package_import(
    workspace_id: int,
    archive: Annotated[UploadFile, File(...)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectTemplateImportValidationResult:
    """预检项目模板包导入，不写入数据库。"""

    await WorkspaceService(session).ensure_access(workspace_id, user_id=current.user.id)
    archive_content = await archive.read()
    return await ProjectTemplatePackageService(session).validate_import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
    )


@router.post(
    "/workspaces/{workspace_id}/template-packages/import",
    response_model=ProjectTemplateImportResult,
)
async def import_project_template_package(
    workspace_id: int,
    archive: Annotated[UploadFile, File(...)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectTemplateImportResult:
    """正式导入项目模板包，导入结果始终是新项目。"""

    await WorkspaceService(session).ensure_access(workspace_id, user_id=current.user.id)
    archive_content = await archive.read()
    return await ProjectTemplatePackageService(session).import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
        operator_id=current.user.id,
    )


@router.post(
    "/workspaces/{workspace_id}/template-packages/preview-artifact",
    response_model=PreviewArtifactResponse,
    response_model_exclude_none=True,
)
async def create_project_template_package_preview_artifact(
    workspace_id: int,
    archive: Annotated[UploadFile, File(...)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """为上传的项目模板包生成临时预览 artifact，不导入项目。"""

    await WorkspaceService(session).ensure_access(workspace_id, user_id=current.user.id)
    archive_content = await archive.read()
    return await ProjectTemplatePackageService(session).create_package_preview_artifact(
        workspace_id=workspace_id,
        archive_content=archive_content,
        tenant_id=f"tenant_{current.user.id}",
    )


def build_template_package_content_disposition(filename: str) -> str:
    """构建兼容中文文件名的下载响应头。"""

    fallback = "".join(
        char if char.isascii() and char not in {'"', "\\", ";"} else "-"
        for char in filename
    ).strip("-")
    safe_fallback = fallback or "project-template.wptemplate.zip"
    return f"attachment; filename=\"{safe_fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
