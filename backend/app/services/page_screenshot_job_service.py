"""文件功能：管理页面截图异步任务队列、任务组进度和后台执行循环。"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import Counter
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.enums import PageFileType, RecordStatus
from app.models.page import Page
from app.models.page_screenshot_job import PageScreenshotJob
from app.schemas.page import (
    PageScreenshotBatchFailure,
    PageScreenshotJobGroupResponse,
    PageScreenshotJobResponse,
)
from app.services.auth_service import AuthContext
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_service import PageScreenshotResult, PageScreenshotService
from app.services.page_service import PageService
from app.services.project_config_service import ProjectConfigService
from app.services.project_service import ProjectService
from app.services.redis_runtime_client import get_redis_runtime_client

ACTIVE_SCREENSHOT_JOB_STATUSES = ("pending", "running")
TERMINAL_SCREENSHOT_JOB_STATUSES = {"succeeded", "failed", "skipped"}
MAX_SCREENSHOT_JOB_ATTEMPTS = 2
SCREENSHOT_JOB_LOCK_PREFIX = "runtime:screenshot-job-lock"
logger = logging.getLogger(__name__)


class PageScreenshotJobService:
    """页面截图任务服务，负责创建、查询和等待队列任务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.page_service = PageService(session)
        self.screenshot_service = PageScreenshotService(session, page_service=self.page_service)
        self.project_config_service = ProjectConfigService(session)
        self.object_storage_service = ObjectStorageService()

    async def create_page_screenshot_job(
        self,
        *,
        page_id: int,
        current: AuthContext,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        source: str = "manual",
    ) -> PageScreenshotJobResponse:
        """创建或复用单页截图任务。"""

        page = await self.page_service._get_page_or_raise(page_id)
        await self.page_service._ensure_page_access(page, user_id=current.user.id)
        self.screenshot_service._validate_page_screenshot_supported(page)
        snapshot = await self.screenshot_service.screenshot_fingerprint_service.build_page_snapshot(page)
        viewport = self.screenshot_service.viewport_resolver.resolve(
            page,
            project_page_config=snapshot.page_config,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        job = await self._get_or_create_job(
            page=page,
            source=source,
            created_by=current.user.id,
            config_hash=snapshot.config_hash,
            viewport=viewport,
            job_group_id=None,
        )
        await self.session.commit()
        await self.session.refresh(job)
        return PageScreenshotJobResponse.model_validate(job)

    async def create_batch_refresh_screenshot_jobs(
        self,
        *,
        project_id: int,
        current: AuthContext,
        source: str = "batch_refresh",
    ) -> PageScreenshotJobGroupResponse:
        """为项目中缺失或过期的 Vue 页面创建截图任务组。"""

        project = await self.project_config_service.get_active_project_or_raise(project_id)
        await ProjectService(self.session).get(project_id, user_id=current.user.id)
        snapshot = await self.screenshot_service.screenshot_fingerprint_service.build_project_snapshot(project)
        pages = await self._list_project_pages_for_batch_screenshot_refresh(project_id)
        target_pages = [
            page for page in pages
            if not self.screenshot_service._is_page_screenshot_current_for_hash(page, snapshot.config_hash)
        ]
        group_id = uuid.uuid4().hex
        jobs: list[PageScreenshotJob] = []

        for page in target_pages:
            viewport = self.screenshot_service.viewport_resolver.resolve(page, project_page_config=snapshot.page_config)
            jobs.append(await self._get_or_create_job(
                page=page,
                source=source,
                created_by=current.user.id,
                config_hash=snapshot.config_hash,
                viewport=viewport,
                job_group_id=group_id,
            ))

        await self.session.commit()
        refreshed_jobs = await self._list_jobs_by_ids([job.id for job in jobs])
        return self._build_group_response(group_id=group_id, jobs=refreshed_jobs)

    async def get_job_response(self, *, job_id: int, current: AuthContext) -> PageScreenshotJobResponse:
        """读取单个截图任务，并校验当前用户有页面访问权。"""

        job = await self.get_job_by_id(job_id)
        await self.page_service.get(job.page_id, user_id=current.user.id)
        return PageScreenshotJobResponse.model_validate(job)

    async def get_group_response(self, *, group_id: str, current: AuthContext) -> PageScreenshotJobGroupResponse:
        """读取截图任务组聚合进度，并校验当前用户有页面访问权。"""

        jobs = await self._list_jobs_by_group_id(group_id)
        if not jobs:
            raise AppException(status_code=404, code="PAGE_SCREENSHOT_JOB_GROUP_NOT_FOUND", detail="截图任务组不存在。")
        for job in jobs:
            await self.page_service.get(job.page_id, user_id=current.user.id)
        return self._build_group_response(group_id=group_id, jobs=jobs)

    async def get_job_by_id(self, job_id: int) -> PageScreenshotJob:
        """按 ID 读取截图任务。"""

        stmt = select(PageScreenshotJob).where(PageScreenshotJob.id == job_id)
        job = (await self.session.execute(stmt)).scalar_one_or_none()
        if job is None:
            raise AppException(status_code=404, code="PAGE_SCREENSHOT_JOB_NOT_FOUND", detail="截图任务不存在。")
        return job

    async def ensure_latest_page_screenshot_via_queue(
        self,
        *,
        page_id: int,
        user_id: int,
        workspace_id: int,
        project_id: int | None = None,
    ) -> PageScreenshotResult:
        """通过队列确保页面截图最新；AI 工具使用该入口等待图片可读。"""

        page = await self.page_service._get_page_or_raise(page_id)
        self.screenshot_service._validate_page_screenshot_supported(page)
        self.screenshot_service._ensure_page_within_scope(page, workspace_id=workspace_id, project_id=project_id)
        cached = await self._try_build_current_result(page)
        if cached is not None:
            return cached

        snapshot = await self.screenshot_service.screenshot_fingerprint_service.build_page_snapshot(page)
        viewport = self.screenshot_service.viewport_resolver.resolve(page, project_page_config=snapshot.page_config)
        job = await self._get_or_create_job(
            page=page,
            source="ai",
            created_by=user_id,
            config_hash=snapshot.config_hash,
            viewport=viewport,
            job_group_id=None,
        )
        await self.session.commit()
        await self.wait_for_job_terminal(
            job.id,
            timeout_seconds=self.settings.page_screenshot_ai_wait_timeout_seconds,
        )

        refreshed_page = await self.page_service._get_page_or_raise(page_id)
        content = await self.object_storage_service.read_object(str(refreshed_page.screenshot_storage_key))
        return await self.screenshot_service._build_result(page=refreshed_page, content=content, refreshed=True)

    async def wait_for_job_terminal(self, job_id: int, *, timeout_seconds: float) -> PageScreenshotJob:
        """轮询等待截图任务进入终态；失败或超时抛出业务异常。"""

        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() <= deadline:
            job = await self.get_job_by_id(job_id)
            if job.status in TERMINAL_SCREENSHOT_JOB_STATUSES:
                if job.status in {"succeeded", "skipped"}:
                    return job
                raise AppException(
                    status_code=502,
                    code=job.error_code or "PAGE_SCREENSHOT_JOB_FAILED",
                    detail=job.error_message or "页面截图任务执行失败。",
                )
            await asyncio.sleep(0.5)
            self.session.expire_all()

        raise AppException(status_code=504, code="PAGE_SCREENSHOT_JOB_TIMEOUT", detail="页面截图任务等待超时。")

    async def claim_pending_jobs(self, *, limit: int) -> list[PageScreenshotJob]:
        """领取待执行截图任务，并写入 running 状态。"""

        stmt = (
            select(PageScreenshotJob)
            .where(PageScreenshotJob.status == "pending")
            .order_by(PageScreenshotJob.created_at.asc(), PageScreenshotJob.id.asc())
            .limit(max(1, limit))
        )
        candidates = list((await self.session.execute(stmt)).scalars().all())
        claimed: list[PageScreenshotJob] = []

        for job in candidates:
            if not await self._acquire_job_lock(job.id):
                continue
            job.status = "running"
            job.attempt_count += 1
            job.error_code = None
            job.error_message = None
            job.started_at = utc_now()
            job.finished_at = None
            claimed.append(job)

        if claimed:
            await self.session.commit()
            for job in claimed:
                await self.session.refresh(job)
        return claimed

    async def run_claimed_job(self, job_id: int) -> None:
        """执行一个已领取的截图任务，并持久化终态。"""

        job = await self.get_job_by_id(job_id)
        if job.status != "running":
            return

        try:
            page = await self.page_service._get_page_or_raise(job.page_id)
            self.screenshot_service._validate_page_screenshot_supported(page)
            await self.screenshot_service._capture_and_store_page_screenshot(
                page,
                operator_id=job.created_by or 0,
                viewport_width=job.viewport_width,
                viewport_height=job.viewport_height,
            )
            job.status = "succeeded"
            job.error_code = None
            job.error_message = None
            job.finished_at = utc_now()
            await self.session.commit()
            logger.info(
                "页面截图任务执行成功。",
                extra={"event": "page.screenshot.job.succeeded", "job_id": job.id, "page_id": job.page_id},
            )
        except Exception as error:  # noqa: BLE001
            await self._mark_job_failed(job, error)
            logger.exception(
                "页面截图任务执行失败。",
                extra={"event": "page.screenshot.job.failed", "job_id": job.id, "page_id": job.page_id},
            )
        finally:
            await self._release_job_lock(job_id)

    async def recover_interrupted_jobs(self) -> int:
        """恢复启动前遗留的 running 截图任务。"""

        stmt = select(PageScreenshotJob).where(PageScreenshotJob.status == "running")
        jobs = list((await self.session.execute(stmt)).scalars().all())
        for job in jobs:
            if job.attempt_count < MAX_SCREENSHOT_JOB_ATTEMPTS:
                job.status = "pending"
                job.error_code = None
                job.error_message = None
                job.started_at = None
                job.finished_at = None
                await self._release_job_lock(job.id)
                continue
            job.status = "failed"
            job.error_code = "PAGE_SCREENSHOT_JOB_INTERRUPTED"
            job.error_message = "页面截图任务因服务重启中断。"
            job.finished_at = utc_now()
            await self._release_job_lock(job.id)
        if jobs:
            await self.session.commit()
        return len(jobs)

    async def _get_or_create_job(
        self,
        *,
        page: Page,
        source: str,
        created_by: int | None,
        config_hash: str,
        viewport: CaptureViewport,
        job_group_id: str | None,
    ) -> PageScreenshotJob:
        """按页面、配置和视口复用活跃任务；不存在时创建新任务。"""

        existing = await self._get_active_job(
            page_id=page.id,
            config_hash=config_hash,
            viewport=viewport,
        )
        if existing is not None:
            if job_group_id and not existing.job_group_id:
                existing.job_group_id = job_group_id
            return existing

        job = PageScreenshotJob(
            job_group_id=job_group_id,
            source=source,
            page_id=page.id,
            workspace_id=page.workspace_id,
            project_id=page.project_id,
            viewport_width=viewport.width,
            viewport_height=viewport.height,
            config_hash=config_hash,
            status="pending",
            attempt_count=0,
            created_by=created_by,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def _get_active_job(
        self,
        *,
        page_id: int,
        config_hash: str,
        viewport: CaptureViewport,
    ) -> PageScreenshotJob | None:
        """读取同页面、同配置、同视口仍在执行链路中的截图任务。"""

        stmt = (
            select(PageScreenshotJob)
            .where(
                PageScreenshotJob.page_id == page_id,
                PageScreenshotJob.config_hash == config_hash,
                PageScreenshotJob.viewport_width == viewport.width,
                PageScreenshotJob.viewport_height == viewport.height,
                PageScreenshotJob.status.in_(ACTIVE_SCREENSHOT_JOB_STATUSES),
            )
            .order_by(PageScreenshotJob.created_at.asc(), PageScreenshotJob.id.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _try_build_current_result(self, page: Page) -> PageScreenshotResult | None:
        """当前截图缓存可用时直接构造结果。"""

        if not await self.screenshot_service._is_page_screenshot_current(page):
            return None
        try:
            content = await self.object_storage_service.read_object(str(page.screenshot_storage_key))
        except AppException as exc:
            if exc.status_code == 404:
                return None
            raise
        return await self.screenshot_service._build_result(page=page, content=content, refreshed=False)

    async def _list_project_pages_for_batch_screenshot_refresh(self, project_id: int) -> list[Page]:
        """读取项目中可批量刷新截图的启用 Vue 页面。"""

        result = await self.session.scalars(
            select(Page)
            .where(Page.project_id == project_id)
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(Page.file_type == PageFileType.VUE.value)
            .where(Page.deleted_at.is_(None))
            .order_by(Page.updated_at.desc(), Page.id.desc())
        )
        return list(result.all())

    async def _list_jobs_by_ids(self, job_ids: Iterable[int]) -> list[PageScreenshotJob]:
        """按 ID 列表读取截图任务。"""

        ids = list(dict.fromkeys(job_ids))
        if not ids:
            return []
        stmt = select(PageScreenshotJob).where(PageScreenshotJob.id.in_(ids)).order_by(PageScreenshotJob.id.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def _list_jobs_by_group_id(self, group_id: str) -> list[PageScreenshotJob]:
        """按任务组 ID 读取截图任务。"""

        stmt = (
            select(PageScreenshotJob)
            .where(PageScreenshotJob.job_group_id == group_id)
            .order_by(PageScreenshotJob.created_at.asc(), PageScreenshotJob.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    def _build_group_response(self, *, group_id: str, jobs: list[PageScreenshotJob]) -> PageScreenshotJobGroupResponse:
        """把一组任务聚合为前端可轮询的进度响应。"""

        counter = Counter(job.status for job in jobs)
        pending_count = counter.get("pending", 0)
        running_count = counter.get("running", 0)
        succeeded_count = counter.get("succeeded", 0)
        failed_count = counter.get("failed", 0)
        skipped_count = counter.get("skipped", 0)
        requested_count = len(jobs)
        if pending_count > 0:
            status = "pending"
        elif running_count > 0:
            status = "running"
        elif failed_count > 0 and succeeded_count + skipped_count > 0:
            status = "partial"
        elif failed_count > 0:
            status = "failed"
        else:
            status = "succeeded"

        return PageScreenshotJobGroupResponse(
            job_group_id=group_id,
            status=status,
            requested_count=requested_count,
            pending_count=pending_count,
            running_count=running_count,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            page_ids=[job.page_id for job in jobs if job.status in {"succeeded", "skipped"}],
            jobs=[PageScreenshotJobResponse.model_validate(job) for job in jobs],
            failures=[
                PageScreenshotBatchFailure(
                    page_id=job.page_id,
                    code=str(job.page_id),
                    detail=job.error_message or "页面截图任务执行失败。",
                )
                for job in jobs
                if job.status == "failed"
            ],
        )

    async def _mark_job_failed(self, job: PageScreenshotJob, error: Exception) -> None:
        """把异常压缩为截图任务失败状态。"""

        if isinstance(error, AppException):
            job.error_code = error.code
            job.error_message = error.detail
        else:
            job.error_code = "PAGE_SCREENSHOT_JOB_FAILED"
            job.error_message = str(error) or "页面截图任务执行失败。"
        job.status = "failed"
        job.finished_at = utc_now()
        await self.session.commit()

    async def _acquire_job_lock(self, job_id: int) -> bool:
        """抢占截图任务执行锁，避免多进程重复执行同一任务。"""

        runtime = get_redis_runtime_client()
        acquired = await asyncio.to_thread(
            runtime.client.set,
            _build_job_lock_key(job_id),
            "1",
            ex=self.settings.page_screenshot_job_lease_seconds,
            nx=True,
        )
        return bool(acquired)

    async def _release_job_lock(self, job_id: int) -> None:
        """释放截图任务执行锁；TTL 仍作为进程异常兜底。"""

        await asyncio.to_thread(get_redis_runtime_client().client.delete, _build_job_lock_key(job_id))


async def run_page_screenshot_queue_loop(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """按配置持续领取并执行页面截图队列任务。"""

    settings = get_settings()
    factory = session_factory or get_session_factory()
    poll_interval = max(0.1, settings.page_screenshot_queue_poll_interval_seconds)
    concurrency = max(1, settings.page_screenshot_queue_concurrency)
    logger.info(
        "页面截图队列后台任务已启动。",
        extra={"event": "page.screenshot.queue.started", "concurrency": concurrency},
    )
    while True:
        try:
            async with factory() as session:
                claimed = await PageScreenshotJobService(session).claim_pending_jobs(limit=concurrency)
            if not claimed:
                await asyncio.sleep(poll_interval)
                continue
            await asyncio.gather(*[run_page_screenshot_job(job.id, session_factory=factory) for job in claimed])
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("页面截图队列循环异常。", extra={"event": "page.screenshot.queue.failed"})
            await asyncio.sleep(poll_interval)


async def run_page_screenshot_job(
    job_id: int,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """使用独立数据库会话执行单个截图任务。"""

    factory = session_factory or get_session_factory()
    async with factory() as session:
        await PageScreenshotJobService(session).run_claimed_job(job_id)


async def recover_interrupted_screenshot_jobs_on_startup(session_factory) -> int:
    """应用启动时收敛仍标记 running 的截图任务。"""

    async with session_factory() as session:
        recovered_count = await PageScreenshotJobService(session).recover_interrupted_jobs()
    if recovered_count:
        logger.warning(
            "已恢复中断的页面截图任务。",
            extra={"event": "page.screenshot.jobs.recovered", "count": recovered_count},
        )
    return recovered_count


def _build_job_lock_key(job_id: int) -> str:
    """构造截图任务执行锁 key。"""

    return get_redis_runtime_client().key(f"{SCREENSHOT_JOB_LOCK_PREFIX}:{job_id}")
