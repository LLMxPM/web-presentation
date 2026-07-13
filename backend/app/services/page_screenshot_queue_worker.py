"""文件功能：运行页面截图后台队列、任务租约心跳和启动恢复流程。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.page_screenshot_job_service import PageScreenshotJobService

logger = logging.getLogger(__name__)
_ACTIVE_SCREENSHOT_JOB_TASKS: set[asyncio.Task[None]] = set()


def start_page_screenshot_job_task(
    job_id: int,
    *,
    worker_id: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> asyncio.Task[None]:
    """创建并登记真实执行任务，关闭或 HTTP 断连时仍可等待其安全收敛。"""

    task = asyncio.create_task(
        run_page_screenshot_job(job_id, worker_id=worker_id, session_factory=session_factory),
        name=f"page-screenshot-job-{job_id}",
    )
    _ACTIVE_SCREENSHOT_JOB_TASKS.add(task)
    task.add_done_callback(_discard_completed_screenshot_job_task)
    return task


def _discard_completed_screenshot_job_task(task: asyncio.Task[None]) -> None:
    """移除已结束任务并记录未向调用方传播的执行异常。"""

    _ACTIVE_SCREENSHOT_JOB_TASKS.discard(task)
    if task.cancelled():
        return
    try:
        error = task.exception()
    except Exception:  # noqa: BLE001
        return
    if error is not None:
        logger.error(
            "页面截图后台任务异常结束。",
            extra={"event": "page.screenshot.job.unhandled_exception", "task_name": task.get_name()},
            exc_info=(type(error), error, error.__traceback__),
        )


async def drain_page_screenshot_jobs() -> None:
    """等待已认领截图任务真实结束，再允许应用关闭 Chromium 池。"""

    # 等待期间可能正好有请求内的“提交并等待”任务完成认领。每轮重新取快照，
    # 防止首轮快照结束后直接关闭浏览器池，导致新登记任务在无槽位状态下继续运行。
    while tasks := tuple(_ACTIVE_SCREENSHOT_JOB_TASKS):
        logger.info(
            "页面截图队列正在等待已认领任务安全结束。",
            extra={"event": "page.screenshot.queue.draining", "active_count": len(tasks)},
        )
        await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)
        # 让 done callback 先从活动集合移除已结束任务，再检查是否有新登记任务。
        await asyncio.sleep(0)


async def run_page_screenshot_queue_loop(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """按配置持续领取并执行页面截图队列任务。"""

    settings = get_settings()
    factory = session_factory or get_session_factory()
    poll_interval = max(0.1, settings.page_screenshot_queue_poll_interval_seconds)
    concurrency = max(1, settings.page_screenshot_queue_concurrency)
    recovery_interval = max(1.0, min(float(getattr(settings, "durable_job_heartbeat_seconds", 30)), 30.0))
    last_recovery_at = 0.0
    logger.info(
        "页面截图队列后台任务已启动。",
        extra={"event": "page.screenshot.queue.started", "concurrency": concurrency},
    )
    while True:
        try:
            async with factory() as session:
                service = PageScreenshotJobService(session)
                if monotonic() - last_recovery_at >= recovery_interval:
                    await service.recover_interrupted_jobs()
                    last_recovery_at = monotonic()
                claimed = await service.claim_pending_jobs(limit=concurrency)
            if not claimed:
                await asyncio.sleep(poll_interval)
                continue
            job_tasks = [
                start_page_screenshot_job_task(job.id, worker_id=job.worker_id, session_factory=factory)
                for job in claimed
                if job.worker_id
            ]
            # 单个任务的基础设施异常不能在关闭期间吞掉队列循环的取消信号；
            # return_exceptions 同时保证其余已认领任务仍会安全收敛。
            batch = asyncio.gather(*job_tasks, return_exceptions=True)
            try:
                # 外层取消只停止后续认领；已进入 Chromium 的任务必须持有槽位直到
                # Context 真正关闭并完成数据库终态提交，不能提前释放其租约。
                await asyncio.shield(batch)
            except asyncio.CancelledError:
                logger.info(
                    "页面截图队列收到关闭信号，停止认领并等待已认领任务。",
                    extra={"event": "page.screenshot.queue.stop_requested", "active_count": len(job_tasks)},
                )
                try:
                    await asyncio.shield(batch)
                finally:
                    # 即使某个任务执行失败，也必须把应用关闭信号继续向上传递。
                    raise
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("页面截图队列循环异常。", extra={"event": "page.screenshot.queue.failed"})
            await asyncio.sleep(poll_interval)


async def run_page_screenshot_job(
    job_id: int,
    *,
    worker_id: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """使用独立数据库会话执行任务，并通过另一个短会话定期续租。"""

    factory = session_factory or get_session_factory()
    async with factory() as session:
        service = PageScreenshotJobService(session, worker_id=worker_id)
        job = await service.get_job_by_id(job_id)
        owner = worker_id or job.worker_id
        if not owner:
            return
        lease_lost = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _run_page_screenshot_job_heartbeat(
                job_id=job_id,
                worker_id=owner,
                session_factory=factory,
                lease_lost=lease_lost,
            ),
            name=f"page-screenshot-job-heartbeat-{job_id}",
        )
        try:
            await service.run_claimed_job(job_id, worker_id=owner, lease_lost=lease_lost)
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task


async def recover_interrupted_screenshot_jobs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """应用启动时只恢复租约已过期的 running 截图任务。"""

    async with session_factory() as session:
        recovered_count = await PageScreenshotJobService(session).recover_interrupted_jobs()
    if recovered_count:
        logger.warning(
            "已恢复中断的页面截图任务。",
            extra={"event": "page.screenshot.jobs.recovered", "count": recovered_count},
        )
    return recovered_count


async def _run_page_screenshot_job_heartbeat(
    *,
    job_id: int,
    worker_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    lease_lost: asyncio.Event,
) -> None:
    """使用短会话续租；无法确认租约时通知主执行流放弃最终页面写入。"""

    settings = get_settings()
    lease_seconds = max(
        1,
        int(getattr(settings, "durable_job_lease_seconds", settings.page_screenshot_job_lease_seconds)),
    )
    configured_interval = int(getattr(settings, "durable_job_heartbeat_seconds", max(1, lease_seconds // 3)))
    interval_seconds = max(1, min(configured_interval, max(1, lease_seconds // 2)))
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as session:
                renewed = await PageScreenshotJobService(session, worker_id=worker_id).renew_job_lease(
                    job_id=job_id,
                    worker_id=worker_id,
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception(
                "页面截图任务心跳续租失败，已禁止当前执行者提交最终页面写入。",
                extra={"event": "page.screenshot.job.heartbeat_failed", "job_id": job_id},
            )
            lease_lost.set()
            return
        if not renewed:
            lease_lost.set()
            return
