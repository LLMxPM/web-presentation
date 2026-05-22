"""文件功能：提供工作空间字体配置的增删改查接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query, require_workspace_access
from app.db.session import get_db_session
from app.schemas.common import ListQuery, MessageResponse, PagedResponse
from app.schemas.font import (
    WorkspaceFontConfigCreateRequest,
    WorkspaceFontConfigResponse,
    WorkspaceFontConfigUpdateRequest,
)
from app.services.auth_service import AuthContext
from app.services.asset_service import AssetService
from app.services.workspace_font_service import WorkspaceFontService

router = APIRouter(dependencies=[Depends(require_workspace_access)])


@router.get("/workspaces/{workspace_id}/fonts", response_model=PagedResponse[WorkspaceFontConfigResponse])
async def list_workspace_fonts(
    workspace_id: int,
    query: Annotated[ListQuery, Depends(get_list_query)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PagedResponse[WorkspaceFontConfigResponse]:
    """列出工作空间下的全部字体配置。"""

    return await WorkspaceFontService(session).list_workspace_fonts(workspace_id, query)


@router.post("/workspaces/{workspace_id}/fonts", response_model=WorkspaceFontConfigResponse)
async def create_workspace_font(
    workspace_id: int,
    payload: WorkspaceFontConfigCreateRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceFontConfigResponse:
    """创建新的工作空间字体配置。"""

    return await WorkspaceFontService(session).create_workspace_font(workspace_id, payload)


@router.patch("/workspaces/{workspace_id}/fonts/{font_id}", response_model=WorkspaceFontConfigResponse)
async def update_workspace_font(
    workspace_id: int,
    font_id: int,
    payload: WorkspaceFontConfigUpdateRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceFontConfigResponse:
    """更新工作空间字体配置。"""

    return await WorkspaceFontService(session).update_workspace_font(workspace_id, font_id, payload)


@router.delete("/workspaces/{workspace_id}/fonts/{font_id}", response_model=MessageResponse)
async def delete_workspace_font(
    workspace_id: int,
    font_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    delete_asset: Annotated[bool, Query(description="是否一并硬删除关联字体文件。")] = False,
) -> MessageResponse:
    """删除工作空间字体配置。"""

    if delete_asset:
        await AssetService(session).delete_workspace_font_with_asset(workspace_id, font_id)
        return MessageResponse(message="字体注册和字体文件已删除。")

    await WorkspaceFontService(session).delete_workspace_font(workspace_id, font_id)
    return MessageResponse(message="字体配置已删除。")


@router.delete("/workspaces/{workspace_id}/font-assets/{asset_id}", response_model=MessageResponse)
async def delete_workspace_font_asset(
    workspace_id: int,
    asset_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """硬删除未注册字体文件。"""

    await AssetService(session).delete_unregistered_font_asset(workspace_id, asset_id)
    return MessageResponse(message="字体文件已删除。")
