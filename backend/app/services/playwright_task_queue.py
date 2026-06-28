"""文件功能：提供 Backend 进程内 Playwright 任务统一并发队列。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from app.core.config import get_settings

_P = ParamSpec("_P")
_R = TypeVar("_R")
logger = logging.getLogger(__name__)


class PlaywrightTaskQueue:
    """统一限制 Playwright 任务并发，避免多个服务各自启动浏览器造成资源争用。"""

    def __init__(self, concurrency: int | None = None) -> None:
        self._fixed_concurrency = concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None
        self._semaphore_concurrency: int | None = None

    async def run_sync(
        self,
        task_name: str,
        func: Callable[_P, _R],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        """把同步 Playwright 任务放入统一队列，并在线程池内执行后返回结果。"""

        semaphore = self._get_semaphore()
        async with semaphore:
            logger.debug(
                "开始执行 Playwright 任务。",
                extra={"event": "playwright.task.started", "task_name": task_name},
            )
            return await asyncio.to_thread(func, *args, **kwargs)

    def _get_semaphore(self) -> asyncio.Semaphore:
        """按当前事件循环和配置懒加载信号量，兼容测试中的多 loop 场景。"""

        loop = asyncio.get_running_loop()
        concurrency = self._resolve_concurrency()
        if (
            self._semaphore is None
            or self._semaphore_loop is not loop
            or self._semaphore_concurrency != concurrency
        ):
            self._semaphore = asyncio.Semaphore(concurrency)
            self._semaphore_loop = loop
            self._semaphore_concurrency = concurrency
        return self._semaphore

    def _resolve_concurrency(self) -> int:
        """解析队列并发，固定值用于测试，生产值来自应用配置。"""

        if self._fixed_concurrency is not None:
            return max(1, int(self._fixed_concurrency))
        return max(1, int(get_settings().playwright_task_concurrency))


_DEFAULT_PLAYWRIGHT_TASK_QUEUE = PlaywrightTaskQueue()


def get_playwright_task_queue() -> PlaywrightTaskQueue:
    """返回当前进程共享的 Playwright 任务队列。"""

    return _DEFAULT_PLAYWRIGHT_TASK_QUEUE
