"""文件功能：提供资源渲染提示回填任务创建与任务组进度查询接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_workspace_access
from app.db.session import get_db_session
from app.schemas.asset import (
    AssetRenderHintBackfillJobCreateRequest,
    AssetRenderHintBackfillJobGroupResponse,
)
from app.services.asset_render_hint_backfill_job_service import AssetRenderHintBackfillJobService
from app.services.auth_service import AuthContext


router = APIRouter()


@router.post("/workspaces/{workspace_id}/assets/render-hint-backfill-jobs", response_model=AssetRenderHintBackfillJobGroupResponse)
async def create_asset_render_hint_backfill_jobs(
    workspace_id: int,
    request: AssetRenderHintBackfillJobCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _: Annotated[object, Depends(require_workspace_access)],
) -> AssetRenderHintBackfillJobGroupResponse:
    """为工作空间可测量资源创建比例回填任务组。"""

    return await AssetRenderHintBackfillJobService(session).create_backfill_jobs(
        workspace_id=workspace_id,
        current=current,
        asset_types=request.asset_types,
        asset_ids=request.asset_ids,
        mode=request.mode,
        overwrite_manual=request.overwrite_manual,
        source="manual",
    )


@router.get("/asset-render-hint-backfill-job-groups/{group_id}", response_model=AssetRenderHintBackfillJobGroupResponse)
async def get_asset_render_hint_backfill_job_group(
    group_id: str,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetRenderHintBackfillJobGroupResponse:
    """查询资源比例回填任务组聚合进度。"""

    return await AssetRenderHintBackfillJobService(session).get_group_response(group_id=group_id, current=current)
