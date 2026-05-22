"""文件功能：提供工作空间主题库的列表、创建、复制、更新与删除接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query, require_workspace_access
from app.db.session import get_db_session
from app.schemas.common import ListQuery, MessageResponse, PagedResponse
from app.schemas.theme import (
    WorkspaceThemeCopyRequest,
    WorkspaceThemeCreateRequest,
    WorkspaceThemeItem,
    WorkspaceThemeUpdateRequest,
)
from app.services.auth_service import AuthContext
from app.services.workspace_theme_service import WorkspaceThemeService

router = APIRouter(dependencies=[Depends(require_workspace_access)])


@router.get("/workspaces/{workspace_id}/themes", response_model=PagedResponse[WorkspaceThemeItem])
async def list_workspace_themes(
    workspace_id: int,
    query: Annotated[ListQuery, Depends(get_list_query)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PagedResponse[WorkspaceThemeItem]:
    """查询工作空间主题列表。"""

    return await WorkspaceThemeService(session).list(workspace_id, query)


@router.get("/workspaces/{workspace_id}/themes/{theme_id}", response_model=WorkspaceThemeItem)
async def get_workspace_theme(
    workspace_id: int,
    theme_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceThemeItem:
    """查询单个工作空间主题详情。"""

    return await WorkspaceThemeService(session).get(workspace_id, theme_id)


@router.post("/workspaces/{workspace_id}/themes", response_model=WorkspaceThemeItem)
async def create_workspace_theme(
    workspace_id: int,
    payload: WorkspaceThemeCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceThemeItem:
    """创建工作空间主题。"""

    return await WorkspaceThemeService(session).create(workspace_id, payload, current.user.id)


@router.post("/workspaces/{workspace_id}/themes/{theme_id}/copy", response_model=WorkspaceThemeItem)
async def copy_workspace_theme(
    workspace_id: int,
    theme_id: int,
    payload: WorkspaceThemeCopyRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceThemeItem:
    """复制工作空间主题。"""

    return await WorkspaceThemeService(session).copy(workspace_id, theme_id, payload, current.user.id)


@router.patch("/workspaces/{workspace_id}/themes/{theme_id}", response_model=WorkspaceThemeItem)
async def update_workspace_theme(
    workspace_id: int,
    theme_id: int,
    payload: WorkspaceThemeUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceThemeItem:
    """更新工作空间主题。"""

    return await WorkspaceThemeService(session).update(workspace_id, theme_id, payload, current.user.id)


@router.delete("/workspaces/{workspace_id}/themes/{theme_id}", response_model=MessageResponse)
async def delete_workspace_theme(
    workspace_id: int,
    theme_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """删除工作空间主题。"""

    await WorkspaceThemeService(session).delete(workspace_id, theme_id)
    return MessageResponse(message="主题已删除。")
