"""文件功能：提供项目列表、创建、更新、删除与结构化路由接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query
from app.db.session import get_db_session
from app.schemas.common import ListQuery, MessageResponse, PagedResponse
from app.schemas.project import ProjectCreateRequest, ProjectItem, ProjectUpdateRequest
from app.schemas.project_route import ProjectRouteTreeResponse, ProjectRouteTreeWriteRequest
from app.services.auth_service import AuthContext
from app.services.project_service import ProjectService
from app.services.project_route_service import ProjectRouteService

router = APIRouter()


@router.get("", response_model=PagedResponse[ProjectItem])
async def list_projects(
    query: Annotated[ListQuery, Depends(get_list_query)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    workspace_id: Annotated[int | None, Query()] = None,
) -> PagedResponse[ProjectItem]:
    """查询项目列表，并支持按工作空间筛选。"""

    return await ProjectService(session).list(query, workspace_id, user_id=current.user.id)


@router.get("/{project_id}", response_model=ProjectItem)
async def get_project(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectItem:
    """获取指定项目详情。"""

    return await ProjectService(session).get(project_id, user_id=current.user.id)


@router.post("", response_model=ProjectItem)
async def create_project(
    payload: ProjectCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectItem:
    """创建项目。"""

    return await ProjectService(session).create(payload, current.user.id)


@router.patch("/{project_id}", response_model=ProjectItem)
async def update_project(
    project_id: int,
    payload: ProjectUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectItem:
    """更新指定项目。"""

    return await ProjectService(session).update(project_id, payload, current.user.id)


@router.get("/{project_id}/routes", response_model=ProjectRouteTreeResponse)
async def get_project_routes(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRouteTreeResponse:
    """读取项目的结构化路由树。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    return await ProjectRouteService(session).get_tree(project_id)


@router.put("/{project_id}/routes", response_model=ProjectRouteTreeResponse)
async def replace_project_routes(
    project_id: int,
    payload: ProjectRouteTreeWriteRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRouteTreeResponse:
    """按整树覆盖方式保存项目路由。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    return await ProjectRouteService(session).replace_tree(project_id, payload, current.user.id)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """删除指定项目。"""

    await ProjectService(session).delete(project_id, user_id=current.user.id)
    return MessageResponse(message="项目已删除。")
