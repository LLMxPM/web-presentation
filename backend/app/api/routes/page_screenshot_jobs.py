"""文件功能：提供页面截图任务和任务组的顶层查询接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.schemas.page import PageScreenshotJobGroupResponse, PageScreenshotJobResponse
from app.services.auth_service import AuthContext
from app.services.page_screenshot_job_service import PageScreenshotJobService

router = APIRouter()


@router.get("/page-screenshot-jobs/{job_id}", response_model=PageScreenshotJobResponse)
async def get_page_screenshot_job(
    job_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageScreenshotJobResponse:
    """查询单个页面截图任务状态。"""

    return await PageScreenshotJobService(session).get_job_response(job_id=job_id, current=current)


@router.get("/page-screenshot-job-groups/{group_id}", response_model=PageScreenshotJobGroupResponse)
async def get_page_screenshot_job_group(
    group_id: str,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PageScreenshotJobGroupResponse:
    """查询页面截图任务组聚合进度。"""

    return await PageScreenshotJobService(session).get_group_response(group_id=group_id, current=current)
