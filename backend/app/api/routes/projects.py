"""文件功能：提供项目列表、创建、更新、删除与结构化路由接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query
from app.db.session import get_db_session
from app.schemas.common import ListQuery, MessageResponse, PagedResponse
from app.schemas.component import SuggestedComponentsResponse, SuggestedComponentsUpdateRequest
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectItem,
    ProjectSuggestedReferenceAssetsResponse,
    ProjectSuggestedReferenceAssetsUpdateRequest,
    ProjectUpdateRequest,
)
from app.schemas.project_route import ProjectRouteTreeResponse, ProjectRouteTreeWriteRequest
from app.services.auth_service import AuthContext
from app.services.project_service import ProjectService
from app.services.project_route_service import ProjectRouteService
from app.services.project_suggested_reference_asset_service import ProjectSuggestedReferenceAssetService
from app.services.suggested_component_service import SuggestedComponentService

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


@router.get("/{project_id}/suggested-reference-assets", response_model=ProjectSuggestedReferenceAssetsResponse)
async def list_project_suggested_reference_assets(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectSuggestedReferenceAssetsResponse:
    """读取项目建议引用内容资源列表。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    items = await ProjectSuggestedReferenceAssetService(session).list_asset_items(project_id)
    return ProjectSuggestedReferenceAssetsResponse(items=items)


@router.put("/{project_id}/suggested-reference-assets", response_model=ProjectSuggestedReferenceAssetsResponse)
async def replace_project_suggested_reference_assets(
    project_id: int,
    payload: ProjectSuggestedReferenceAssetsUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectSuggestedReferenceAssetsResponse:
    """覆盖保存项目建议引用内容资源列表。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    items = await ProjectSuggestedReferenceAssetService(session).replace_assets(project_id, payload.asset_ids)
    return ProjectSuggestedReferenceAssetsResponse(items=items)


@router.get("/{project_id}/suggested-components", response_model=SuggestedComponentsResponse)
async def list_project_suggested_components(
    project_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuggestedComponentsResponse:
    """读取项目建议组件快照列表。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    items = await SuggestedComponentService(session).list_project_component_items(project_id)
    return SuggestedComponentsResponse(items=items)


@router.put("/{project_id}/suggested-components", response_model=SuggestedComponentsResponse)
async def replace_project_suggested_components(
    project_id: int,
    payload: SuggestedComponentsUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SuggestedComponentsResponse:
    """覆盖保存项目建议组件快照列表。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    items = await SuggestedComponentService(session).replace_project_components(project_id, payload.component_ids)
    return SuggestedComponentsResponse(items=items)


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
