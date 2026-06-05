"""文件功能：提供工作空间样式库的列表、创建、复制、更新与删除接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query, require_workspace_access
from app.db.session import get_db_session
from app.schemas.common import ListQuery, MessageResponse, PagedResponse
from app.schemas.component import SuggestedComponentsResponse, SuggestedComponentsUpdateRequest
from app.schemas.workspace_style import (
    WorkspaceStyleCopyRequest,
    WorkspaceStyleCreateRequest,
    WorkspaceStyleExportPackageRequest,
    WorkspaceStyleImportResult,
    WorkspaceStyleImportValidationResult,
    WorkspaceStyleItem,
    WorkspaceStyleUpdateRequest,
)
from app.services.auth_service import AuthContext
from app.services.workspace_style_package_service import WorkspaceStylePackageService
from app.services.workspace_style_service import WorkspaceStyleService
from app.services.suggested_component_service import SuggestedComponentService

router = APIRouter(dependencies=[Depends(require_workspace_access)])


@router.get("/workspaces/{workspace_id}/styles", response_model=PagedResponse[WorkspaceStyleItem])
async def list_workspace_styles(
    workspace_id: int,
    query: Annotated[ListQuery, Depends(get_list_query)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PagedResponse[WorkspaceStyleItem]:
    """查询工作空间样式列表。"""

    return await WorkspaceStyleService(session).list(workspace_id, query)


@router.post("/workspaces/{workspace_id}/styles/export-package")
async def export_workspace_style_package(
    workspace_id: int,
    payload: WorkspaceStyleExportPackageRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """导出工作空间样式离线包。"""

    archive_content, filename = await WorkspaceStylePackageService(session).export_package(
        workspace_id=workspace_id,
        style_ids=payload.style_ids,
    )
    return Response(
        content=archive_content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/workspaces/{workspace_id}/styles/import-package/validate", response_model=WorkspaceStyleImportValidationResult)
async def validate_workspace_style_package_import(
    workspace_id: int,
    archive: Annotated[UploadFile, File(...)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceStyleImportValidationResult:
    """预检样式离线包，不写入数据库。"""

    archive_content = await archive.read()
    return await WorkspaceStylePackageService(session).validate_import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
    )


@router.post("/workspaces/{workspace_id}/styles/import-package", response_model=WorkspaceStyleImportResult)
async def import_workspace_style_package(
    workspace_id: int,
    archive: Annotated[UploadFile, File(...)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceStyleImportResult:
    """正式导入样式离线包。"""

    archive_content = await archive.read()
    return await WorkspaceStylePackageService(session).import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
        operator_id=current.user.id,
    )


@router.get("/workspaces/{workspace_id}/styles/{style_id}", response_model=WorkspaceStyleItem)
async def get_workspace_style(
    workspace_id: int,
    style_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceStyleItem:
    """查询单个工作空间样式详情。"""

    return await WorkspaceStyleService(session).get(workspace_id, style_id)


@router.get("/workspaces/{workspace_id}/styles/{style_id}/suggested-components", response_model=SuggestedComponentsResponse)
async def list_workspace_style_suggested_components(
    workspace_id: int,
    style_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuggestedComponentsResponse:
    """读取工作空间样式建议组件列表。"""

    items = await SuggestedComponentService(session).list_style_component_items(
        workspace_id,
        style_id,
        include_unavailable=True,
    )
    return SuggestedComponentsResponse(items=items)


@router.put("/workspaces/{workspace_id}/styles/{style_id}/suggested-components", response_model=SuggestedComponentsResponse)
async def replace_workspace_style_suggested_components(
    workspace_id: int,
    style_id: int,
    payload: SuggestedComponentsUpdateRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuggestedComponentsResponse:
    """覆盖保存工作空间样式建议组件列表。"""

    items = await SuggestedComponentService(session).replace_style_components(
        workspace_id,
        style_id,
        payload.component_ids,
    )
    return SuggestedComponentsResponse(items=items)


@router.post("/workspaces/{workspace_id}/styles", response_model=WorkspaceStyleItem)
async def create_workspace_style(
    workspace_id: int,
    payload: WorkspaceStyleCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceStyleItem:
    """创建工作空间样式。"""

    return await WorkspaceStyleService(session).create(workspace_id, payload, current.user.id)


@router.post("/workspaces/{workspace_id}/styles/{style_id}/copy", response_model=WorkspaceStyleItem)
async def copy_workspace_style(
    workspace_id: int,
    style_id: int,
    payload: WorkspaceStyleCopyRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceStyleItem:
    """复制工作空间样式。"""

    return await WorkspaceStyleService(session).copy(workspace_id, style_id, payload, current.user.id)


@router.patch("/workspaces/{workspace_id}/styles/{style_id}", response_model=WorkspaceStyleItem)
async def update_workspace_style(
    workspace_id: int,
    style_id: int,
    payload: WorkspaceStyleUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceStyleItem:
    """更新工作空间样式。"""

    return await WorkspaceStyleService(session).update(workspace_id, style_id, payload, current.user.id)


@router.delete("/workspaces/{workspace_id}/styles/{style_id}", response_model=MessageResponse)
async def delete_workspace_style(
    workspace_id: int,
    style_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """删除工作空间样式。"""

    await WorkspaceStyleService(session).delete(workspace_id, style_id)
    return MessageResponse(message="样式已删除。")
