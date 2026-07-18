"""文件功能：提供页面可视化编辑预览 artifact 创建与批量保存接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.schemas.page_visual_edit import (
    PageVisualEditApplyRequest,
    PageVisualEditApplyResponse,
    PageVisualEditPreviewArtifactCreateRequest,
    PageVisualEditPreviewArtifactResponse,
)
from app.services.auth_service import AuthContext
from app.services.page_visual_edit_service import PageVisualEditService


router = APIRouter()


@router.post(
    "/{page_id}/visual-edit/apply",
    response_model=PageVisualEditApplyResponse,
    response_model_by_alias=False,
)
async def apply_page_visual_edit(
    page_id: int,
    payload: PageVisualEditApplyRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageVisualEditApplyResponse:
    """校验编辑 artifact 和源码基线，整批应用操作并保存一个新页面版本。"""

    return await PageVisualEditService(session).apply(
        page_id=page_id,
        payload=payload,
        user_id=current.user.id,
    )


@router.post(
    "/{page_id}/visual-edit/preview-artifacts",
    response_model=PageVisualEditPreviewArtifactResponse,
    response_model_by_alias=False,
)
async def create_page_visual_edit_preview_artifact(
    page_id: int,
    payload: PageVisualEditPreviewArtifactCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageVisualEditPreviewArtifactResponse:
    """基于 Backend 当前页面版本创建只读分析和节点选择所需的编辑态 artifact。"""

    return await PageVisualEditService(session).create_preview_artifact(
        page_id=page_id,
        payload=payload,
        user_id=current.user.id,
    )
