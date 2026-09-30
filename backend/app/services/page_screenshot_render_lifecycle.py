"""文件功能：关联截图快照与远程渲染请求，将持久化取消传播到 Renderer，覆盖先取消后入队的竞争。"""

from __future__ import annotations

import asyncio
import logging

from render_contracts.constants import OPERATION_PAGE_CAPTURE, REQUEST_TERMINAL_STATUSES
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.time_utils import utc_now
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.render_request import RenderRequest
from app.services.rendering.request_service import RenderRequestService

logger = logging.getLogger(__name__)


def screenshot_render_owner_key(*, page_id: int, version_no: int, config_hash: str, width: int, height: int) -> str:
    """生成同一截图快照的稳定关联键；与 BrowserCaptureService 的 128 字符边界一致。"""
    return f"page-screenshot:{page_id}:v{version_no}:{config_hash}:{width}x{height}"[:128]


async def cancel_screenshot_render_requests(session: AsyncSession, job: PageScreenshotJob) -> int:
    """只取消当前工作空间、页面和截图快照的未终态请求；提交由调用方决定。"""
    key = screenshot_render_owner_key(page_id=job.page_id, version_no=job.target_page_version_no,
                                      config_hash=job.config_hash, width=job.viewport_width, height=job.viewport_height)
    ids = list(await session.scalars(select(RenderRequest.id).where(
        RenderRequest.workspace_id == job.workspace_id, RenderRequest.page_id == job.page_id,
        RenderRequest.logical_owner_key == key, RenderRequest.business_stage == "page.screenshot",
        RenderRequest.operation == OPERATION_PAGE_CAPTURE,
        RenderRequest.status.notin_(tuple(REQUEST_TERMINAL_STATUSES)),
        RenderRequest.cancel_requested.is_(False),
    )))
    service = RenderRequestService(session)
    for request_id in ids:
        await service.cancel_request(request_id)
    return len(ids)


async def watch_screenshot_cancellation(*, job_id: int, worker_id: str,
                                        session_factory: async_sessionmaker[AsyncSession]) -> None:
    """短会话轮询持久化取消，直到请求入队或执行结束；失去 Job 租约后不影响新执行者。"""
    while True:
        try:
            async with session_factory() as session:
                job = await session.get(PageScreenshotJob, job_id)
                if (job is None or job.status != "running" or job.worker_id != worker_id or
                        job.lease_expires_at is None or job.lease_expires_at <= utc_now()):
                    return
                if job.cancel_requested_at is not None:
                    await cancel_screenshot_render_requests(session, job)
                    await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("截图取消传播暂时失败，下一轮重试。", extra={"event": "page.screenshot.cancel.propagate_failed", "job_id": job_id})
        await asyncio.sleep(0.5)
