"""文件功能：管理页面截图任务组、成员关系及批次进度聚合。"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.page_screenshot_job_group import PageScreenshotJobGroup, PageScreenshotJobGroupItem
from app.schemas.page import PageScreenshotBatchFailure, PageScreenshotJobGroupResponse, PageScreenshotJobResponse


class PageScreenshotJobGroupService:
    """封装截图任务组持久化，允许一个活跃任务被多个批次复用。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_group(
        self,
        *,
        group_id: str,
        source: str,
        workspace_id: int | None,
        project_id: int | None,
        created_by: int | None,
    ) -> PageScreenshotJobGroup:
        """创建持久化任务组，确保没有目标页面的批次仍可查询。"""

        group = PageScreenshotJobGroup(
            id=group_id,
            source=source,
            workspace_id=workspace_id,
            project_id=project_id,
            created_by=created_by,
        )
        self.session.add(group)
        await self.session.flush()
        return group

    async def get_group_by_id(self, group_id: str) -> PageScreenshotJobGroup:
        """按 ID 读取任务组，不以是否存在成员判断批次是否存在。"""

        group = await self.session.get(PageScreenshotJobGroup, group_id)
        if group is None:
            raise AppException(status_code=404, code="PAGE_SCREENSHOT_JOB_GROUP_NOT_FOUND", detail="截图任务组不存在。")
        return group

    async def attach_job(self, *, group_id: str, job_id: int) -> None:
        """建立任务组成员关系，重复附加保持幂等。"""

        existing = await self.session.scalar(
            select(PageScreenshotJobGroupItem.id).where(
                PageScreenshotJobGroupItem.group_id == group_id,
                PageScreenshotJobGroupItem.job_id == job_id,
            )
        )
        if existing is None:
            self.session.add(PageScreenshotJobGroupItem(group_id=group_id, job_id=job_id))
            await self.session.flush()

    async def list_jobs(self, group_id: str) -> list[PageScreenshotJob]:
        """通过成员表读取批次任务，兼容任务被多个批次同时复用。"""

        stmt = (
            select(PageScreenshotJob)
            .join(PageScreenshotJobGroupItem, PageScreenshotJobGroupItem.job_id == PageScreenshotJob.id)
            .where(PageScreenshotJobGroupItem.group_id == group_id)
            .order_by(PageScreenshotJob.created_at.asc(), PageScreenshotJob.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    @staticmethod
    def build_response(*, group_id: str, jobs: list[PageScreenshotJob]) -> PageScreenshotJobGroupResponse:
        """聚合任务组状态；运行中优先于待执行，空批次直接成功。"""

        counter = Counter(job.status for job in jobs)
        pending_count = counter.get("pending", 0)
        running_count = counter.get("running", 0)
        succeeded_count = counter.get("succeeded", 0)
        failed_count = counter.get("failed", 0)
        skipped_count = counter.get("skipped", 0)
        cancelled_count = counter.get("cancelled", 0)
        if running_count:
            status = "running"
        elif pending_count:
            status = "pending"
        elif failed_count + cancelled_count and succeeded_count + skipped_count:
            status = "partial"
        elif failed_count:
            status = "failed"
        elif cancelled_count:
            status = "cancelled"
        else:
            status = "succeeded"

        return PageScreenshotJobGroupResponse(
            job_group_id=group_id,
            status=status,
            requested_count=len(jobs),
            pending_count=pending_count,
            running_count=running_count,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            cancelled_count=cancelled_count,
            page_ids=[job.page_id for job in jobs if job.status in {"succeeded", "skipped"}],
            jobs=[PageScreenshotJobResponse.model_validate(job) for job in jobs],
            failures=[
                PageScreenshotBatchFailure(
                    page_id=job.page_id,
                    code=job.error_code or "PAGE_SCREENSHOT_JOB_FAILED",
                    detail=job.error_message or "页面截图任务执行失败。",
                )
                for job in jobs
                if job.status == "failed"
            ],
        )
