"""文件功能：提供工作空间列表、创建、更新与删除接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query
from app.db.session import get_db_session
from app.schemas.common import ListQuery, MessageResponse, PagedResponse
from app.schemas.workspace import WorkspaceCreateRequest, WorkspaceItem, WorkspaceUpdateRequest
from app.services.auth_service import AuthContext
from app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.get("", response_model=PagedResponse[WorkspaceItem])
async def list_workspaces(
    query: Annotated[ListQuery, Depends(get_list_query)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PagedResponse[WorkspaceItem]:
    """查询工作空间列表。"""

    return await WorkspaceService(session).list(query, user_id=current.user.id)


@router.get("/{workspace_id}", response_model=WorkspaceItem)
async def get_workspace(
    workspace_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceItem:
    """获取指定工作空间信息。"""

    return await WorkspaceService(session).get(workspace_id, user_id=current.user.id)


@router.post("", response_model=WorkspaceItem)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceItem:
    """创建工作空间。"""

    return await WorkspaceService(session).create(payload, current.user.id)


@router.patch("/{workspace_id}", response_model=WorkspaceItem)
async def update_workspace(
    workspace_id: int,
    payload: WorkspaceUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceItem:
    """更新指定工作空间。"""

    return await WorkspaceService(session).update(workspace_id, payload, current.user.id)


@router.put("/{workspace_id}/touch", response_model=WorkspaceItem)
async def touch_workspace(
    workspace_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceItem:
    """更新工作空间的最后访问时间。"""

    return await WorkspaceService(session).touch(workspace_id, user_id=current.user.id)


@router.delete("/{workspace_id}", response_model=MessageResponse)
async def delete_workspace(
    workspace_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """删除指定工作空间。"""

    await WorkspaceService(session).delete(workspace_id, user_id=current.user.id)
    return MessageResponse(message="工作空间已删除。")
