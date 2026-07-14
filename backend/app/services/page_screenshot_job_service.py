"""文件功能：管理页面截图异步任务队列、任务组进度和后台执行循环。"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.enums import PageFileType, RecordStatus
from app.models.page import Page
from app.models.page_screenshot_job import PageScreenshotJob
from app.schemas.page import (
    PageScreenshotJobGroupResponse,
    PageScreenshotJobResponse,
)
from app.services.auth_service import AuthContext
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.durable_job_lease_service import (
    DurableJobRecoverySummary,
    build_durable_worker_id,
    claim_pending_jobs as claim_durable_jobs,
    is_sqlite_lock_error,
    recover_expired_running_jobs,
    renew_running_job_lease,
    request_job_cancellation,
    transition_owned_running_job,
)
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_job_group_service import PageScreenshotJobGroupService
from app.services.page_screenshot_service import (
    PageScreenshotCaptureArtifact,
    PageScreenshotResult,
    PageScreenshotService,
)
from app.services.page_service import PageService
from app.services.project_config_service import ProjectConfigService
from app.services.project_service import ProjectService

ACTIVE_SCREENSHOT_JOB_STATUSES = ("pending", "running")
TERMINAL_SCREENSHOT_JOB_STATUSES = {"succeeded", "failed", "skipped", "cancelled"}
MAX_SCREENSHOT_JOB_ATTEMPTS = 3
SQLITE_LOCK_RETRY_ATTEMPTS = 3
PAGE_SCREENSHOT_JOB_STALE_CODE = "PAGE_SCREENSHOT_JOB_STALE"
logger = logging.getLogger(__name__)


class PageScreenshotJobService:
    """页面截图任务服务，负责创建、查询和等待队列任务。"""

    def __init__(self, session: AsyncSession, *, worker_id: str | None = None) -> None:
        """绑定短生命周期数据库会话，并为领取任务生成唯一执行者标识。"""

        self.session = session
        self.settings = get_settings()
        self.worker_id = worker_id or build_durable_worker_id()
        self.page_service = PageService(session)
        self.screenshot_service = PageScreenshotService(session, page_service=self.page_service)
        self.project_config_service = ProjectConfigService(session)
        self.object_storage_service = ObjectStorageService()
        self.job_group_service = PageScreenshotJobGroupService(session)

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
            target_page_version_no=page.current_version_no,
            config_hash=snapshot.config_hash,
            viewport=viewport,
            job_group_id=None,
        )
        await self.session.commit()
        await self.session.refresh(job)
        response = PageScreenshotJobResponse.model_validate(job)
        # refresh 会打开新的只读事务；同步等待前立即结束它，避免 SQLite 读事务滞留。
        await self.session.rollback()
        return response

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
            if not self.screenshot_service._is_page_screenshot_current_for_hash(
                page,
                snapshot.config_hash,
                viewport=self.screenshot_service.viewport_resolver.resolve(
                    page,
                    project_page_config=snapshot.page_config,
                ),
            )
        ]
        group_id = uuid.uuid4().hex
        await self.job_group_service.create_group(
            group_id=group_id,
            source=source,
            workspace_id=project.workspace_id,
            project_id=project.id,
            created_by=current.user.id,
        )
        jobs: list[PageScreenshotJob] = []

        for page in target_pages:
            viewport = self.screenshot_service.viewport_resolver.resolve(page, project_page_config=snapshot.page_config)
            jobs.append(await self._get_or_create_job(
                page=page,
                source=source,
                created_by=current.user.id,
                target_page_version_no=page.current_version_no,
                config_hash=snapshot.config_hash,
                viewport=viewport,
                job_group_id=group_id,
            ))

        await self.session.commit()
        refreshed_jobs = await self._list_jobs_by_ids([job.id for job in jobs])
        response = self.job_group_service.build_response(group_id=group_id, jobs=refreshed_jobs)
        # 任务已持久化，响应构造后释放读取会话，后台 Worker 可立即写入状态。
        await self.session.rollback()
        return response

    async def get_job_response(self, *, job_id: int, current: AuthContext) -> PageScreenshotJobResponse:
        """读取单个截图任务，并校验当前用户有页面访问权。"""

        job = await self.get_job_by_id(job_id)
        await self.page_service.get(job.page_id, user_id=current.user.id)
        return PageScreenshotJobResponse.model_validate(job)

    async def get_group_response(self, *, group_id: str, current: AuthContext) -> PageScreenshotJobGroupResponse:
        """读取截图任务组聚合进度，并校验当前用户有页面访问权。"""

        group = await self.job_group_service.get_group_by_id(group_id)
        if group.project_id is not None:
            await ProjectService(self.session).get(group.project_id, user_id=current.user.id)
        jobs = await self.job_group_service.list_jobs(group_id)
        return self.job_group_service.build_response(group_id=group_id, jobs=jobs)

    async def cancel_job(self, *, job_id: int, current: AuthContext) -> PageScreenshotJobResponse:
        """请求取消截图任务；运行中任务会在写入页面前确认取消。"""

        job = await self.get_job_by_id(job_id)
        await self.page_service.get(job.page_id, user_id=current.user.id)
        await request_job_cancellation(self.session, PageScreenshotJob, job_id=job_id)
        self.session.expire_all()
        return PageScreenshotJobResponse.model_validate(await self.get_job_by_id(job_id))

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
            target_page_version_no=page.current_version_no,
            config_hash=snapshot.config_hash,
            viewport=viewport,
            job_group_id=None,
        )
        await self.session.commit()
        terminal = await self.wait_for_job_terminal_detached(
            job.id,
            timeout_seconds=self.settings.page_screenshot_ai_wait_timeout_seconds,
        )
        self._raise_if_job_stale(terminal)

        self.session.expire_all()
        refreshed_page = await self.page_service._get_page_or_raise(page_id)
        content = await self.object_storage_service.read_object(str(refreshed_page.screenshot_storage_key))
        return await self.screenshot_service._build_result(page=refreshed_page, content=content, refreshed=True)

    async def wait_for_job_terminal(self, job_id: int, *, timeout_seconds: float) -> PageScreenshotJob:
        """兼容旧调用：等待过程使用短 Session，终态才在当前会话读取一次。"""

        terminal = await self.wait_for_job_terminal_detached(job_id, timeout_seconds=timeout_seconds)
        self._raise_if_job_stale(terminal)
        if terminal.status in {"succeeded", "skipped"}:
            self.session.expire_all()
            return await self.get_job_by_id(job_id)
        if terminal.status == "cancelled":
            raise AppException(status_code=409, code="PAGE_SCREENSHOT_JOB_CANCELLED", detail="页面截图任务已取消。")
        raise AppException(
            status_code=502,
            code=terminal.error_code or "PAGE_SCREENSHOT_JOB_FAILED",
            detail=terminal.error_message or "页面截图任务执行失败。",
        )

    @classmethod
    async def wait_for_job_terminal_detached(
        cls,
        job_id: int,
        *,
        timeout_seconds: float,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> PageScreenshotJobResponse:
        """使用短 Session 等待任务；无后台 Worker 时以内联租约执行，旧同步接口也不会绕过队列。"""

        jobs = await cls.wait_for_jobs_terminal_detached(
            [job_id],
            timeout_seconds=timeout_seconds,
            session_factory=session_factory,
        )
        return jobs[0]

    @classmethod
    async def wait_for_jobs_terminal_detached(
        cls,
        job_ids: Iterable[int],
        *,
        timeout_seconds: float,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> list[PageScreenshotJobResponse]:
        """用短 Session 等待一组任务；每轮最多内联领取一个任务以限制 SQLite 写入压力。"""

        from app.db.session import get_session_factory
        from app.services.page_screenshot_queue_worker import start_page_screenshot_job_task

        ordered_ids = list(dict.fromkeys(job_ids))
        if not ordered_ids:
            return []
        factory = session_factory or get_session_factory()
        worker_id = build_durable_worker_id()
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() <= deadline:
            async with factory() as session:
                service = cls(session, worker_id=worker_id)
                jobs = await service._list_jobs_by_ids(ordered_ids)
                jobs_by_id = {job.id: job for job in jobs}
                if len(jobs_by_id) != len(ordered_ids):
                    raise AppException(status_code=404, code="PAGE_SCREENSHOT_JOB_NOT_FOUND", detail="截图任务不存在。")
                if all(job.status in TERMINAL_SCREENSHOT_JOB_STATUSES for job in jobs):
                    return [PageScreenshotJobResponse.model_validate(jobs_by_id[job_id]) for job_id in ordered_ids]
                pending_job_id = next((job_id for job_id in ordered_ids if jobs_by_id[job_id].status == "pending"), None)
                claimed = (
                    await service._claim_specific_pending_job(pending_job_id)
                    if pending_job_id is not None
                    else False
                )
            if claimed:
                execution_task = start_page_screenshot_job_task(
                    pending_job_id,
                    worker_id=worker_id,
                    session_factory=factory,
                )
                try:
                    # 浏览器断开或 HTTP 请求取消不能中断已经认领的任务；后台任务会
                    # 继续持有浏览器槽位和租约，直到安全提交终态。
                    await asyncio.shield(execution_task)
                except asyncio.CancelledError:
                    raise
                continue
            await asyncio.sleep(0.25)
        raise AppException(status_code=504, code="PAGE_SCREENSHOT_JOB_TIMEOUT", detail="页面截图任务等待超时。")

    async def claim_pending_jobs(self, *, limit: int) -> list[PageScreenshotJob]:
        """通过数据库条件更新原子领取待执行任务，并写入可续期租约。"""

        job_ids = await claim_durable_jobs(
            self.session,
            PageScreenshotJob,
            worker_id=self.worker_id,
            limit=limit,
            lease_seconds=self._lease_seconds,
        )
        return await self._list_jobs_by_ids(job_ids)

    async def _claim_specific_pending_job(self, job_id: int) -> bool:
        """以同一数据库租约协议领取指定 pending Job，供兼容同步接口安全等待。"""

        job_ids = await claim_durable_jobs(
            self.session,
            PageScreenshotJob,
            worker_id=self.worker_id,
            limit=1,
            lease_seconds=self._lease_seconds,
            candidate_query=(
                select(PageScreenshotJob.id)
                .where(PageScreenshotJob.id == job_id, PageScreenshotJob.status == "pending")
            ),
        )
        return bool(job_ids)

    async def run_claimed_job(
        self,
        job_id: int,
        *,
        worker_id: str | None = None,
        lease_lost: asyncio.Event | None = None,
    ) -> None:
        """执行已领取任务；捕获仅执行一次，SQLite 重试只覆盖最终数据库提交。"""

        job = await self.get_job_by_id(job_id)
        owner = worker_id or job.worker_id
        if job.status != "running" or not owner or job.worker_id != owner or self._is_lease_lost(lease_lost):
            return
        page_id = job.page_id
        execution_started_at = time.monotonic()
        if job.cancel_requested_at is not None:
            await self._acknowledge_cancelled_job(job_id=job_id, worker_id=owner)
            return

        try:
            page = await self.page_service._get_page_or_raise(job.page_id)
            self.screenshot_service._validate_page_screenshot_supported(page)
            if not await self._is_job_snapshot_current(page=page, job=job):
                await self._mark_job_stale(job_id=job_id, worker_id=owner)
                return
            artifact = await self.screenshot_service.capture_page_screenshot_artifact(
                page=page,
                operator_id=job.created_by or 0,
                target_page_version_no=job.target_page_version_no,
                config_hash=job.config_hash,
                viewport=CaptureViewport(width=job.viewport_width, height=job.viewport_height),
            )
        except Exception as error:  # noqa: BLE001
            await self.session.rollback()
            await self._mark_job_failed_or_retry(job_id=job_id, worker_id=owner, error=error)
            logger.exception(
                "页面截图任务捕获失败。",
                extra={"event": "page.screenshot.job.failed", "job_id": job_id, "page_id": page_id},
            )
            return

        if self._is_lease_lost(lease_lost):
            await self.session.rollback()
            return

        try:
            await self._finalize_captured_job(
                job=job,
                worker_id=owner,
                artifact=artifact,
                lease_lost=lease_lost,
                execution_started_at=execution_started_at,
            )
        except Exception as error:  # noqa: BLE001
            await self.session.rollback()
            await self._mark_job_failed_or_retry(job_id=job_id, worker_id=owner, error=error)
            logger.exception(
                "页面截图任务最终写入失败。",
                extra={"event": "page.screenshot.job.failed", "job_id": job_id, "page_id": page_id},
            )

    async def _is_job_snapshot_current(self, *, page: Page, job: PageScreenshotJob) -> bool:
        """校验页面版本和展示配置仍与入队任务快照一致，避免捕获过期内容。"""

        if int(page.current_version_no) != int(job.target_page_version_no):
            return False
        snapshot = await self.screenshot_service.screenshot_fingerprint_service.build_page_snapshot(page)
        return snapshot.config_hash == job.config_hash

    async def _finalize_captured_job(
        self,
        *,
        job: PageScreenshotJob,
        worker_id: str,
        artifact: PageScreenshotCaptureArtifact,
        lease_lost: asyncio.Event | None,
        execution_started_at: float,
    ) -> None:
        """以短事务发布已捕获对象；SQLite 锁只重试本阶段，绝不再次启动 Chromium。"""

        job_id = int(job.id)
        page_id = int(job.page_id)
        operator_id = int(job.created_by or 0)
        for attempt in range(SQLITE_LOCK_RETRY_ATTEMPTS):
            if self._is_lease_lost(lease_lost):
                return
            try:
                if not await self._is_artifact_snapshot_current(page_id=page_id, artifact=artifact):
                    await self.session.rollback()
                    await self._mark_job_stale(job_id=job_id, worker_id=worker_id)
                    return
                published_at = utc_now()
                page_updated = await self.session.execute(
                    update(Page)
                    .where(
                        Page.id == page_id,
                        Page.current_version_no == artifact.page_version_no,
                    )
                    .values(
                        screenshot_storage_key=artifact.storage_key,
                        screenshot_version_no=artifact.page_version_no,
                        screenshot_config_hash=artifact.config_hash,
                        screenshot_viewport_width=artifact.viewport_width,
                        screenshot_viewport_height=artifact.viewport_height,
                        screenshot_updated_at=published_at,
                        updated_by=operator_id,
                    )
                    .execution_options(synchronize_session=False)
                )
                if (page_updated.rowcount or 0) != 1:
                    await self.session.rollback()
                    await self._mark_job_stale(job_id=job_id, worker_id=worker_id)
                    return
                if self._is_lease_lost(lease_lost):
                    await self.session.rollback()
                    return
                completed = await transition_owned_running_job(
                    self.session,
                    PageScreenshotJob,
                    job_id=job_id,
                    worker_id=worker_id,
                    require_not_cancelled=True,
                    require_active_lease=True,
                    commit=False,
                    values={
                        "status": "succeeded",
                        "error_code": None,
                        "error_message": None,
                        "lease_expires_at": None,
                        "heartbeat_at": None,
                        "finished_at": published_at,
                    },
                )
                if not completed:
                    await self.session.rollback()
                    return
                await self.session.commit()
                logger.info(
                    "页面截图任务执行成功。",
                    extra={
                        "event": "page.screenshot.job.succeeded",
                        "job_id": job_id,
                        "page_id": page_id,
                        "attempt_count": job.attempt_count,
                        "duration_ms": round((time.monotonic() - execution_started_at) * 1000, 2),
                    },
                )
                return
            except OperationalError as error:
                await self.session.rollback()
                if not is_sqlite_lock_error(self.session, error) or attempt + 1 >= SQLITE_LOCK_RETRY_ATTEMPTS:
                    raise
                delay_seconds = 0.05 * (2**attempt)
                logger.warning(
                    "页面截图任务最终写入遇到 SQLite 锁，正在短退避重试。",
                    extra={
                        "event": "page.screenshot.job.sqlite_lock_retry",
                        "job_id": job_id,
                        "attempt": attempt + 1,
                        "delay_seconds": delay_seconds,
                    },
                )
                await asyncio.sleep(delay_seconds)

    async def _is_artifact_snapshot_current(
        self,
        *,
        page_id: int,
        artifact: PageScreenshotCaptureArtifact,
    ) -> bool:
        """在最终发布前重新读取页面和展示配置，避免捕获期变更覆盖当前截图指针。"""

        # 捕获阶段已经提交并释放事务；这里强制丢弃旧 Identity Map，确保读取到最终提交时的快照。
        self.session.expire_all()
        page = (
            await self.session.execute(
                select(Page)
                .where(Page.id == page_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if page is None or int(page.current_version_no) != artifact.page_version_no:
            return False
        snapshot = await self.screenshot_service.screenshot_fingerprint_service.build_page_snapshot(page)
        return snapshot.config_hash == artifact.config_hash

    async def _mark_job_stale(self, *, job_id: int, worker_id: str) -> None:
        """将仍由当前执行者持有但页面快照已过期的任务收敛为 skipped。"""

        skipped = await transition_owned_running_job(
            self.session,
            PageScreenshotJob,
            job_id=job_id,
            worker_id=worker_id,
            require_not_cancelled=True,
            require_active_lease=True,
            values={
                "status": "skipped",
                "lease_expires_at": None,
                "heartbeat_at": None,
                "error_code": PAGE_SCREENSHOT_JOB_STALE_CODE,
                "error_message": "页面版本或展示配置已变化，截图任务不再发布旧快照。",
                "finished_at": utc_now(),
            },
        )
        if not skipped:
            await self.session.rollback()
            await self._acknowledge_cancelled_job(job_id=job_id, worker_id=worker_id)

    @staticmethod
    def _is_lease_lost(lease_lost: asyncio.Event | None) -> bool:
        """统一判断心跳是否已经确认当前执行者丢失租约。"""

        return lease_lost is not None and lease_lost.is_set()

    async def renew_job_lease(self, *, job_id: int, worker_id: str) -> bool:
        """为当前 Worker 正在执行的截图任务续租。"""

        return await renew_running_job_lease(
            self.session,
            PageScreenshotJob,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=self._lease_seconds,
        )

    async def recover_interrupted_jobs(self) -> int:
        """仅恢复租约已过期的 running 任务，保留其他实例的有效执行权。"""

        summary = await recover_expired_running_jobs(
            self.session,
            PageScreenshotJob,
            max_attempts=MAX_SCREENSHOT_JOB_ATTEMPTS,
            interrupted_error_code="PAGE_SCREENSHOT_JOB_INTERRUPTED",
            interrupted_error_message="页面截图任务的执行租约已过期。",
        )
        self._log_recovery_summary(summary)
        return summary.total_count

    async def _get_or_create_job(
        self,
        *,
        page: Page,
        source: str,
        created_by: int | None,
        target_page_version_no: int,
        config_hash: str,
        viewport: CaptureViewport,
        job_group_id: str | None,
    ) -> PageScreenshotJob:
        """按页面、配置和视口复用活跃任务；不存在时创建新任务。"""

        existing = await self._get_active_job(
            page_id=page.id,
            target_page_version_no=target_page_version_no,
            config_hash=config_hash,
            viewport=viewport,
        )
        if existing is not None:
            if job_group_id and not existing.job_group_id:
                existing.job_group_id = job_group_id
            if job_group_id:
                await self.job_group_service.attach_job(group_id=job_group_id, job_id=existing.id)
            return existing

        try:
            async with self.session.begin_nested():
                job = PageScreenshotJob(
                    job_group_id=job_group_id,
                    source=source,
                    page_id=page.id,
                    workspace_id=page.workspace_id,
                    project_id=page.project_id,
                    viewport_width=viewport.width,
                    viewport_height=viewport.height,
                    target_page_version_no=target_page_version_no,
                    config_hash=config_hash,
                    status="pending",
                    attempt_count=0,
                    created_by=created_by,
                )
                self.session.add(job)
                await self.session.flush()
        except IntegrityError:
            job = await self._get_active_job(
                page_id=page.id,
                target_page_version_no=target_page_version_no,
                config_hash=config_hash,
                viewport=viewport,
            )
            if job is None:
                raise
        if job_group_id:
            await self.job_group_service.attach_job(group_id=job_group_id, job_id=job.id)
        return job

    async def _get_active_job(
        self,
        *,
        page_id: int,
        target_page_version_no: int,
        config_hash: str,
        viewport: CaptureViewport,
    ) -> PageScreenshotJob | None:
        """读取同页面、同配置、同视口仍在执行链路中的截图任务。"""

        stmt = (
            select(PageScreenshotJob)
            .where(
                PageScreenshotJob.page_id == page_id,
                PageScreenshotJob.target_page_version_no == target_page_version_no,
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

    async def _mark_job_failed_or_retry(self, *, job_id: int, worker_id: str, error: Exception) -> None:
        """按错误性质与尝试次数决定重排或失败，并始终校验任务拥有者。"""

        self.session.expire_all()
        job = await self.get_job_by_id(job_id)
        if job.status != "running" or job.worker_id != worker_id:
            return
        if job.cancel_requested_at is not None:
            await self._acknowledge_cancelled_job(job_id=job_id, worker_id=worker_id)
            return

        if isinstance(error, AppException):
            error_code = error.code
            error_message = error.detail
            retryable = error.status_code >= 500
        else:
            error_code = "PAGE_SCREENSHOT_JOB_FAILED"
            error_message = str(error) or "页面截图任务执行失败。"
            retryable = True

        if retryable and job.attempt_count < MAX_SCREENSHOT_JOB_ATTEMPTS:
            values = {
                "status": "pending",
                "worker_id": None,
                "lease_expires_at": None,
                "heartbeat_at": None,
                "error_code": error_code,
                "error_message": error_message,
                "started_at": None,
                "finished_at": None,
            }
        else:
            values = {
                "status": "failed",
                "lease_expires_at": None,
                "error_code": error_code,
                "error_message": error_message,
                "finished_at": utc_now(),
            }
        await transition_owned_running_job(
            self.session,
            PageScreenshotJob,
            job_id=job_id,
            worker_id=worker_id,
            require_active_lease=True,
            values=values,
        )

    async def _acknowledge_cancelled_job(self, *, job_id: int, worker_id: str) -> None:
        """由当前拥有者把已请求取消的运行任务收敛为 cancelled。"""

        await transition_owned_running_job(
            self.session,
            PageScreenshotJob,
            job_id=job_id,
            worker_id=worker_id,
            require_active_lease=True,
            values={
                "status": "cancelled",
                "lease_expires_at": None,
                "heartbeat_at": None,
                "finished_at": utc_now(),
            },
        )

    @staticmethod
    def _raise_if_job_stale(job: PageScreenshotJobResponse) -> None:
        """阻止同步调用把已跳过的旧快照误当作当前截图读取。"""

        if job.status == "skipped" and job.error_code == PAGE_SCREENSHOT_JOB_STALE_CODE:
            raise AppException(
                status_code=409,
                code=PAGE_SCREENSHOT_JOB_STALE_CODE,
                detail=job.error_message or "页面截图任务快照已过期，请重新请求截图。",
            )

    @property
    def _lease_seconds(self) -> int:
        """优先读取通用租约配置，并兼容升级前的截图专用配置。"""

        return max(
            1,
            int(
                getattr(
                    self.settings,
                    "durable_job_lease_seconds",
                    self.settings.page_screenshot_job_lease_seconds,
                )
            ),
        )

    @staticmethod
    def _log_recovery_summary(summary: DurableJobRecoverySummary) -> None:
        """记录过期租约恢复指标，供日志采集侧聚合队列运行情况。"""

        if not summary.total_count:
            return
        logger.warning(
            "页面截图任务过期租约已恢复。",
            extra={
                "event": "page.screenshot.jobs.lease_recovered",
                "requeued_count": summary.requeued_count,
                "failed_count": summary.failed_count,
                "cancelled_count": summary.cancelled_count,
            },
        )


async def run_page_screenshot_queue_loop(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """兼容旧导入路径，委托独立 Worker 模块运行截图队列。"""

    from app.services.page_screenshot_queue_worker import run_page_screenshot_queue_loop as run_loop

    await run_loop(session_factory)


async def run_page_screenshot_job(
    job_id: int,
    *,
    worker_id: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """兼容旧导入路径，委托独立 Worker 模块执行单个任务。"""

    from app.services.page_screenshot_queue_worker import run_page_screenshot_job as run_job

    await run_job(job_id, worker_id=worker_id, session_factory=session_factory)


async def recover_interrupted_screenshot_jobs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """兼容旧导入路径，委托 Worker 模块恢复过期任务。"""

    from app.services.page_screenshot_queue_worker import recover_interrupted_screenshot_jobs_on_startup as recover

    return await recover(session_factory)
