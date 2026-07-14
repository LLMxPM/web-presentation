"""文件功能：提供有界加权调度和固定专属线程的共享 Chromium 浏览器池。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal, ParamSpec, TypeVar, cast
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.playwright_browser_worker import PlaywrightBrowserWorker


_P = ParamSpec("_P")
_R = TypeVar("_R")
PlaywrightTaskPriority = Literal["interactive", "background"]
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _PoolJob:
    """描述一个等待浏览器池槽位的进程内任务。"""

    job_id: str
    task_name: str
    priority: PlaywrightTaskPriority
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    needs_browser: bool
    future: asyncio.Future[Any]
    started: asyncio.Event
    enqueued_at: float


@dataclass(slots=True)
class _PoolSlot:
    """把一个异步调度槽与一条固定线程及浏览器状态绑定。"""

    slot_id: int
    executor: ThreadPoolExecutor
    worker: PlaywrightBrowserWorker


class PlaywrightBrowserPool:
    """统一调度截图和渲染诊断，并在专属线程中复用 Chromium。"""

    def __init__(
        self,
        concurrency: int | None = None,
        *,
        queue_size: int | None = None,
        queue_wait_timeout_seconds: float | None = None,
        browser_reuse_enabled: bool | None = None,
        interactive_weight: int = 3,
    ) -> None:
        self._fixed_concurrency = concurrency
        self._fixed_queue_size = queue_size
        self._fixed_queue_wait_timeout_seconds = queue_wait_timeout_seconds
        self._fixed_browser_reuse_enabled = browser_reuse_enabled
        self._interactive_weight = max(1, int(interactive_weight))
        self._interactive_jobs: deque[_PoolJob] = deque()
        self._background_jobs: deque[_PoolJob] = deque()
        self._interactive_streak = 0
        self._lifecycle_lock: asyncio.Lock | None = None
        self._lifecycle_loop: asyncio.AbstractEventLoop | None = None
        self._state_lock: asyncio.Lock | None = None
        self._jobs_available: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._slots: list[_PoolSlot] = []
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._closing = False
        self._closed_for_submissions = False

    async def start(self, *, allow_reopen: bool = False) -> None:
        """在当前事件循环创建调度槽；仅应用新生命周期可显式重新开放已关闭池。"""

        loop = asyncio.get_running_loop()
        lifecycle_lock = self._get_lifecycle_lock(loop)
        async with lifecycle_lock:
            if self._started:
                if self._loop is not loop:
                    raise RuntimeError("Playwright 浏览器池不能跨事件循环复用。")
                return
            if self._closed_for_submissions:
                if not allow_reopen:
                    raise AppException(
                        status_code=503,
                        code="PLAYWRIGHT_POOL_STOPPING",
                        detail="浏览器池正在关闭。",
                    )
                self._closed_for_submissions = False

            self._loop = loop
            self._state_lock = asyncio.Lock()
            self._jobs_available = asyncio.Event()
            self._closing = False
            settings = get_settings()
            for slot_id in range(self._resolve_concurrency()):
                executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"playwright-browser-{slot_id}")
                worker = PlaywrightBrowserWorker(
                    slot_id=slot_id,
                    executable_path=settings.page_screenshot_browser_executable_path or None,
                    reuse_enabled=self._resolve_reuse_enabled(),
                    recycle_task_count=int(getattr(settings, "playwright_browser_recycle_task_count", 50)),
                    recycle_age_seconds=float(getattr(settings, "playwright_browser_recycle_age_seconds", 1800.0)),
                )
                slot = _PoolSlot(slot_id=slot_id, executor=executor, worker=worker)
                self._slots.append(slot)
                self._worker_tasks.append(
                    asyncio.create_task(self._worker_loop(slot), name=f"playwright-browser-pool-{slot_id}")
                )
            self._started = True
            logger.info(
                "Playwright 浏览器池已启动。",
                extra={
                    "event": "playwright.pool.started",
                    "concurrency": len(self._slots),
                    "queue_size": self._resolve_queue_size(),
                    "reuse_enabled": self._resolve_reuse_enabled(),
                },
            )

    async def stop(self) -> None:
        """拒绝新任务、取消排队项，并等待在途同步任务真正释放槽位。"""

        lifecycle_lock = self._get_lifecycle_lock(asyncio.get_running_loop())
        async with lifecycle_lock:
            # 关闭标记必须早于等待在途任务设置，避免刚进入截图链路的调用在停止后
            # 又通过 _submit 的自动 start() 重新创建一组 Chromium 线程。
            self._closed_for_submissions = True
            if not self._started:
                return
            lock = self._require_lock()
            async with lock:
                self._closing = True
                pending = [*self._interactive_jobs, *self._background_jobs]
                self._interactive_jobs.clear()
                self._background_jobs.clear()
                for job in pending:
                    # 调用方在 started.wait() 阶段也要立即收到关闭错误，不能继续等到
                    # PLAYWRIGHT_TASK_QUEUE_TIMEOUT 才发现任务已经被移出队列。
                    job.started.set()
                    if not job.future.done():
                        job.future.set_exception(
                            AppException(status_code=503, code="PLAYWRIGHT_POOL_STOPPING", detail="浏览器池正在关闭。")
                        )
                self._require_jobs_event().set()

            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            for slot in self._slots:
                slot.executor.shutdown(wait=True, cancel_futures=False)
            self._slots.clear()
            self._worker_tasks.clear()
            self._started = False
            self._loop = None
            self._state_lock = None
            self._jobs_available = None
            logger.info("Playwright 浏览器池已关闭。", extra={"event": "playwright.pool.stopped"})

    async def run_sync(
        self,
        task_name: str,
        func: Callable[_P, _R],
        *args: _P.args,
        priority: PlaywrightTaskPriority = "background",
        **kwargs: _P.kwargs,
    ) -> _R:
        """兼容旧调用：在受控专属线程执行普通同步函数。"""

        return cast(
            _R,
            await self._submit(
                task_name=task_name,
                priority=priority,
                func=func,
                args=tuple(args),
                kwargs=dict(kwargs),
                needs_browser=False,
            ),
        )

    async def run_with_browser(
        self,
        task_name: str,
        func: Callable[..., _R],
        *args: Any,
        priority: PlaywrightTaskPriority = "background",
        **kwargs: Any,
    ) -> _R:
        """把长期浏览器作为第一个参数传给同步函数并返回其结果。"""

        return cast(
            _R,
            await self._submit(
                task_name=task_name,
                priority=priority,
                func=func,
                args=tuple(args),
                kwargs=dict(kwargs),
                needs_browser=True,
            ),
        )

    async def _submit(
        self,
        *,
        task_name: str,
        priority: PlaywrightTaskPriority,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        needs_browser: bool,
    ) -> Any:
        """有界入队并只对排队阶段应用等待超时。"""

        await self.start()
        loop = asyncio.get_running_loop()
        job = _PoolJob(
            job_id=f"pw_{uuid4().hex}",
            task_name=task_name,
            priority=priority,
            func=func,
            args=args,
            kwargs=kwargs,
            needs_browser=needs_browser,
            future=loop.create_future(),
            started=asyncio.Event(),
            enqueued_at=monotonic(),
        )
        lock = self._require_lock()
        async with lock:
            if self._closing:
                raise AppException(status_code=503, code="PLAYWRIGHT_POOL_STOPPING", detail="浏览器池正在关闭。")
            if self._pending_count() >= self._resolve_queue_size():
                logger.warning(
                    "Playwright 任务队列已满。",
                    extra={
                        "event": "playwright.task.queue_full",
                        "task_name": task_name,
                        "priority": priority,
                        "queue_length": self._pending_count(),
                    },
                )
                raise AppException(
                    status_code=429,
                    code="PLAYWRIGHT_TASK_QUEUE_FULL",
                    detail="浏览器任务队列已满，请稍后重试。",
                )
            target = self._interactive_jobs if priority == "interactive" else self._background_jobs
            target.append(job)
            logger.debug(
                "Playwright 任务已入队。",
                extra={
                    "event": "playwright.task.queued",
                    "task_name": task_name,
                    "priority": priority,
                    "queue_length": self._pending_count(),
                },
            )
            self._require_jobs_event().set()

        try:
            try:
                await asyncio.wait_for(
                    job.started.wait(),
                    timeout=self._resolve_queue_wait_timeout_seconds(),
                )
            except TimeoutError:
                if await self._remove_pending(job):
                    logger.warning(
                        "Playwright 任务排队超时。",
                        extra={
                            "event": "playwright.task.queue_timeout",
                            "task_name": task_name,
                            "priority": priority,
                            "wait_ms": round((monotonic() - job.enqueued_at) * 1000, 2),
                        },
                    )
                    raise AppException(
                        status_code=429,
                        code="PLAYWRIGHT_TASK_QUEUE_TIMEOUT",
                        detail="浏览器任务排队超时，请稍后重试。",
                    ) from None
            return await asyncio.shield(job.future)
        except asyncio.CancelledError:
            removed = await self._remove_pending(job)
            if not removed:
                job.future.add_done_callback(self._consume_abandoned_result)
            raise

    async def _worker_loop(self, slot: _PoolSlot) -> None:
        """持续领取加权任务；调用方取消后仍等待线程任务真正结束。"""

        loop = asyncio.get_running_loop()
        try:
            while True:
                job = await self._take_next()
                if job is None:
                    return
                job.started.set()
                started_at = monotonic()
                logger.debug(
                    "开始执行 Playwright 任务。",
                    extra={
                        "event": "playwright.task.started",
                        "task_name": job.task_name,
                        "priority": job.priority,
                        "slot_id": slot.slot_id,
                        "wait_ms": round((started_at - job.enqueued_at) * 1000, 2),
                    },
                )
                try:
                    method = slot.worker.run_with_browser if job.needs_browser else slot.worker.run_plain
                    result = await loop.run_in_executor(slot.executor, method, job.func, job.args, job.kwargs)
                except Exception as error:  # noqa: BLE001
                    if not job.future.done():
                        job.future.set_exception(error)
                else:
                    if not job.future.done():
                        job.future.set_result(result)
                finally:
                    logger.info(
                        "Playwright 任务已结束。",
                        extra={
                            "event": "playwright.task.finished",
                            "task_name": job.task_name,
                            "priority": job.priority,
                            "slot_id": slot.slot_id,
                            "wait_ms": round((started_at - job.enqueued_at) * 1000, 2),
                            "duration_ms": round((monotonic() - started_at) * 1000, 2),
                            "queue_length": self._pending_count(),
                        },
                    )
        finally:
            await loop.run_in_executor(slot.executor, slot.worker.close)

    async def _take_next(self) -> _PoolJob | None:
        """按 3:1 权重领取交互/后台任务，并保证后台任务不会饿死。"""

        while True:
            lock = self._require_lock()
            async with lock:
                job = self._select_weighted_job()
                if job is not None:
                    if self._pending_count() == 0:
                        self._require_jobs_event().clear()
                    return job
                if self._closing:
                    return None
                self._require_jobs_event().clear()
            await self._require_jobs_event().wait()

    def _select_weighted_job(self) -> _PoolJob | None:
        """选择下一个任务；连续三个交互任务后优先让出一次后台槽位。"""

        if self._background_jobs and (
            not self._interactive_jobs or self._interactive_streak >= self._interactive_weight
        ):
            self._interactive_streak = 0
            return self._background_jobs.popleft()
        if self._interactive_jobs:
            self._interactive_streak += 1
            return self._interactive_jobs.popleft()
        if self._background_jobs:
            self._interactive_streak = 0
            return self._background_jobs.popleft()
        return None

    async def _remove_pending(self, target: _PoolJob) -> bool:
        """取消尚未运行的任务；已领取任务必须继续占用槽位至线程结束。"""

        lock = self._require_lock()
        async with lock:
            for queue in (self._interactive_jobs, self._background_jobs):
                try:
                    queue.remove(target)
                except ValueError:
                    continue
                if not target.future.done():
                    target.future.cancel()
                return True
        return False

    def _resolve_concurrency(self) -> int:
        """解析浏览器池槽位数，兼容旧 PLAYWRIGHT_TASK_CONCURRENCY。"""

        if self._fixed_concurrency is not None:
            return max(1, int(self._fixed_concurrency))
        settings = get_settings()
        return max(1, int(getattr(settings, "playwright_browser_pool_size", settings.playwright_task_concurrency)))

    def _resolve_queue_size(self) -> int:
        """解析等待队列上限。"""

        if self._fixed_queue_size is not None:
            return max(1, int(self._fixed_queue_size))
        return max(1, int(getattr(get_settings(), "playwright_task_queue_size", 16)))

    def _resolve_queue_wait_timeout_seconds(self) -> float:
        """解析只作用于等待槽位阶段的超时时间。"""

        if self._fixed_queue_wait_timeout_seconds is not None:
            return max(0.01, float(self._fixed_queue_wait_timeout_seconds))
        return max(0.01, float(getattr(get_settings(), "playwright_task_queue_wait_timeout_seconds", 60.0)))

    def _resolve_reuse_enabled(self) -> bool:
        """解析 Chromium 长期复用熔断开关。"""

        if self._fixed_browser_reuse_enabled is not None:
            return bool(self._fixed_browser_reuse_enabled)
        return bool(getattr(get_settings(), "playwright_browser_reuse_enabled", True))

    def _pending_count(self) -> int:
        """返回等待队列总长度，不包含正在执行的任务。"""

        return len(self._interactive_jobs) + len(self._background_jobs)

    def _require_lock(self) -> asyncio.Lock:
        """返回已初始化锁。"""

        if self._state_lock is None:
            raise RuntimeError("Playwright 浏览器池尚未启动。")
        return self._state_lock

    def _require_jobs_event(self) -> asyncio.Event:
        """返回已初始化任务通知事件。"""

        if self._jobs_available is None:
            raise RuntimeError("Playwright 浏览器池尚未启动。")
        return self._jobs_available

    def _get_lifecycle_lock(self, loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
        """返回当前事件循环的生命周期锁，串行化并发启动与关闭。"""

        if self._lifecycle_lock is None:
            self._lifecycle_lock = asyncio.Lock()
            self._lifecycle_loop = loop
            return self._lifecycle_lock
        if self._lifecycle_loop is not loop:
            if self._started:
                raise RuntimeError("Playwright 浏览器池不能跨事件循环复用。")
            # 已完整停止的池可由新的 FastAPI 生命周期重新初始化；未停止时不允许
            # 跨事件循环接管同一组专属线程。
            self._lifecycle_lock = asyncio.Lock()
            self._lifecycle_loop = loop
        return self._lifecycle_lock

    @staticmethod
    def _consume_abandoned_result(future: asyncio.Future[Any]) -> None:
        """消费已取消调用方留下的结果，避免未读取异常告警。"""

        if future.cancelled():
            return
        try:
            future.exception()
        except Exception:  # noqa: BLE001
            return


_DEFAULT_PLAYWRIGHT_BROWSER_POOL = PlaywrightBrowserPool()


def get_playwright_browser_pool() -> PlaywrightBrowserPool:
    """返回当前 Backend 进程共享的 Chromium 浏览器池。"""

    return _DEFAULT_PLAYWRIGHT_BROWSER_POOL
