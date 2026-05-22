"""文件功能：提供工作空间页面资源库的列表、创建、更新与删除接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_page_list_query
from app.db.session import get_db_session
from app.schemas.common import MessageResponse, PagedResponse
from app.schemas.page import (
    PageCopyToProjectRequest,
    PageCurrentComponentIndex,
    PageCurrentModuleDependencies,
    PageCreateRequest,
    PageItem,
    PageListQuery,
    PageScreenshotRequest,
    PageScreenshotBatchRefreshRequest,
    PageScreenshotBatchRefreshResponse,
    PageSnapshotCreateRequest,
    PageUpdateRequest,
    PageVersionContent,
    PageVersionListItem,
    PageVersionRestoreRequest,
)
from app.schemas.release import PreviewArtifactResponse
from app.services.auth_service import AuthContext
from app.services.page_preview_service import PagePreviewService
from app.services.page_service import PageService
from app.services.page_screenshot_service import PageScreenshotService

router = APIRouter()


@router.get("", response_model=PagedResponse[PageItem])
async def list_pages(
    query: Annotated[PageListQuery, Depends(get_page_list_query)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PagedResponse[PageItem]:
    """查询当前用户可访问的页面资源库列表。"""

    return await PageService(session).list(query, user_id=current.user.id)


@router.get("/{page_id}", response_model=PageItem)
async def get_page(
    page_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """查询单个页面详情。"""

    return await PageService(session).get(page_id, user_id=current.user.id)


@router.get("/{page_id}/component-index", response_model=PageCurrentComponentIndex)
async def get_page_current_component_index(
    page_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageCurrentComponentIndex:
    """查询页面当前版本的组件和资源索引信息。"""

    return await PageService(session).get_current_component_index(page_id, user_id=current.user.id)


@router.get("/{page_id}/module-dependencies", response_model=PageCurrentModuleDependencies)
async def get_page_current_module_dependencies(
    page_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageCurrentModuleDependencies:
    """查询页面当前版本的源码依赖索引。"""

    return await PageService(session).get_current_module_dependencies(page_id, user_id=current.user.id)


@router.post("", response_model=PageItem)
async def create_page(
    payload: PageCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """创建页面资源。"""

    return await PageService(session).create(payload, current.user.id)


@router.post("/{page_id}/copy-to-project", response_model=PageItem)
async def copy_page_to_project(
    page_id: int,
    payload: PageCopyToProjectRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """将当前页面复制到同工作空间内的另一个项目。"""

    return await PageService(session).copy_to_project(page_id, payload, current.user.id)


@router.post("/batch-refresh-screenshots", response_model=PageScreenshotBatchRefreshResponse)
async def batch_refresh_page_screenshots(
    payload: PageScreenshotBatchRefreshRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageScreenshotBatchRefreshResponse:
    """批量刷新指定项目中缺失或已过期的页面截图。"""

    return await PageScreenshotService(session).batch_refresh_project_screenshots(
        project_id=payload.project_id,
        current=current,
    )


@router.patch("/{page_id}", response_model=PageItem)
async def update_page(
    page_id: int,
    payload: PageUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """更新指定页面资源。"""

    return await PageService(session).update(page_id, payload, current.user.id)


@router.get("/{page_id}/versions", response_model=list[PageVersionListItem])
async def list_page_versions(
    page_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[PageVersionListItem]:
    """查询指定页面的版本历史。"""

    return await PageService(session).list_versions(page_id, user_id=current.user.id)


@router.get("/{page_id}/versions/{version_no}", response_model=PageVersionContent)
async def get_page_version_content(
    page_id: int,
    version_no: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageVersionContent:
    """查询指定页面版本的完整源码内容。"""

    return await PageService(session).get_version_content(page_id, version_no, user_id=current.user.id)


@router.post("/{page_id}/versions/{version_no}/preview-artifact", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_page_version_preview_artifact(
    page_id: int,
    version_no: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """基于指定页面历史版本生成单页临时预览 artifact。"""

    await PageService(session).get(page_id, user_id=current.user.id)
    page = await PageService(session)._get_page_or_raise(page_id)
    return await PagePreviewService(session).create_page_version_preview_artifact(
        page=page,
        version_no=version_no,
        user_id=current.user.id,
    )


@router.post("/{page_id}/versions/{version_no}/snapshot", response_model=PageVersionContent)
async def create_page_snapshot(
    page_id: int,
    version_no: int,
    payload: PageSnapshotCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageVersionContent:
    """将指定页面版本提升为重点快照。"""

    await PageService(session).get(page_id, user_id=current.user.id)
    return await PageService(session).create_snapshot(page_id, version_no, payload)


@router.post("/{page_id}/versions/{version_no}/restore", response_model=PageItem)
async def restore_page_version(
    page_id: int,
    version_no: int,
    payload: PageVersionRestoreRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """恢复指定页面版本为当前最新版本。"""

    return await PageService(session).restore_version(page_id, version_no, payload, current.user.id)


@router.post("/{page_id}/screenshot", response_model=PageItem)
async def save_page_screenshot(
    page_id: int,
    payload: PageScreenshotRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageItem:
    """为指定页面保存一张最新截图。"""

    return await PageScreenshotService(session).save_page_screenshot(
        page_id=page_id,
        current=current,
        viewport_width=payload.viewport_width,
        viewport_height=payload.viewport_height,
    )


@router.delete("/{page_id}", response_model=MessageResponse)
async def delete_page(
    page_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """删除指定页面资源。"""

    await PageService(session).delete(page_id, user_id=current.user.id)
    return MessageResponse(message="页面已删除。")
