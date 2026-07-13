"""文件功能：验证 Backend Playwright 浏览器池的并发、权重与取消语义。"""

from __future__ import annotations

import asyncio
import threading
import time
import pytest

from app.core.config import AppSettings
from app.core.exceptions import AppException
from app.services.playwright_task_queue import PlaywrightTaskQueue


async def test_playwright_task_queue_should_limit_all_tasks_together() -> None:
    """截图和交互诊断对应的普通同步任务应受同一并发上限约束。"""

    queue = PlaywrightTaskQueue(concurrency=1, queue_size=4)
    lock = threading.Lock()
    active_count = 0
    max_active_count = 0

    def blocking_result(value: str) -> str:
        """模拟同步 Playwright 任务，并记录线程池内同时执行数量。"""

        nonlocal active_count, max_active_count
        with lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
        try:
            time.sleep(0.05)
            return value
        finally:
            with lock:
                active_count -= 1

    capture_result, diagnostics_result = await asyncio.gather(
        queue.run_sync("page-screenshot", blocking_result, "capture", priority="background"),
        queue.run_sync("page-render-diagnostics", blocking_result, "diagnostics", priority="interactive"),
    )
    await queue.stop()

    assert capture_result == "capture"
    assert diagnostics_result == "diagnostics"
    assert max_active_count == 1


@pytest.mark.asyncio
async def test_cancelled_running_task_should_keep_slot_until_thread_finishes() -> None:
    """调用方取消后，底层线程结束前不得提前执行下一个浏览器任务。"""

    queue = PlaywrightTaskQueue(concurrency=1, queue_size=4)
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()

    def first_job() -> str:
        """阻塞第一个槽位，模拟无法立即取消的同步 Playwright 调用。"""

        first_started.set()
        release_first.wait(timeout=2)
        return "first"

    def second_job() -> str:
        """记录第二项何时真正进入专属线程。"""

        second_started.set()
        return "second"

    first_task = asyncio.create_task(queue.run_sync("first", first_job))
    assert await asyncio.to_thread(first_started.wait, 1)
    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task

    second_task = asyncio.create_task(queue.run_sync("second", second_job))
    await asyncio.sleep(0.05)
    assert not second_started.is_set()

    release_first.set()
    assert await second_task == "second"
    await queue.stop()


@pytest.mark.asyncio
async def test_playwright_task_queue_should_schedule_interactive_and_background_three_to_one() -> None:
    """两类任务同时排队时，应连续执行三个交互任务后让出一个后台任务。"""

    queue = PlaywrightTaskQueue(concurrency=1, queue_size=8)
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    execution_order: list[str] = []

    def blocker() -> str:
        """占住唯一槽位，确保待测任务先完整进入等待队列。"""

        blocker_started.set()
        release_blocker.wait(timeout=2)
        return "blocker"

    def record(name: str) -> str:
        """记录专属线程中的真实领取顺序。"""

        execution_order.append(name)
        return name

    blocker_task = asyncio.create_task(queue.run_sync("blocker", blocker))
    assert await asyncio.to_thread(blocker_started.wait, 1)
    queued = [
        asyncio.create_task(queue.run_sync(f"interactive-{index}", record, f"i{index}", priority="interactive"))
        for index in range(4)
    ]
    queued.extend(
        asyncio.create_task(queue.run_sync(f"background-{index}", record, f"b{index}", priority="background"))
        for index in range(2)
    )
    await asyncio.sleep(0.05)
    release_blocker.set()

    await blocker_task
    await asyncio.gather(*queued)
    await queue.stop()

    assert execution_order == ["i0", "i1", "i2", "b0", "i3", "b1"]


def test_playwright_task_concurrency_should_be_positive() -> None:
    """Playwright 统一并发配置必须为正整数。"""

    assert AppSettings(_env_file=None).playwright_task_concurrency == 1
    assert AppSettings(_env_file=None).playwright_browser_pool_size == 1
    with pytest.raises(ValueError, match="Playwright"):
        AppSettings(_env_file=None, playwright_browser_pool_size=0)


@pytest.mark.asyncio
async def test_stop_should_immediately_wake_queued_call_without_releasing_running_slot() -> None:
    """关闭时排队调用应立即收到 503，在途线程仍须完成后才能停止池。"""

    queue = PlaywrightTaskQueue(concurrency=1, queue_size=4, queue_wait_timeout_seconds=30)
    first_started = threading.Event()
    release_first = threading.Event()

    def first_job() -> str:
        """模拟正在 Chromium 专属线程中执行的任务。"""

        first_started.set()
        release_first.wait(timeout=2)
        return "first"

    first_task = asyncio.create_task(queue.run_sync("first", first_job))
    assert await asyncio.to_thread(first_started.wait, 1)
    queued_task = asyncio.create_task(queue.run_sync("queued", lambda: "queued"))
    await asyncio.sleep(0)

    stopping = asyncio.create_task(queue.stop())
    with pytest.raises(AppException) as error:
        await asyncio.wait_for(queued_task, timeout=0.5)
    assert error.value.code == "PLAYWRIGHT_POOL_STOPPING"
    assert not stopping.done()

    release_first.set()
    assert await first_task == "first"
    await stopping


@pytest.mark.asyncio
async def test_concurrent_start_should_create_only_one_slot_group() -> None:
    """并发首个请求不能重复启动两组浏览器 Worker 线程。"""

    queue = PlaywrightTaskQueue(concurrency=1, queue_size=4)

    await asyncio.gather(queue.start(), queue.start())

    assert len(queue._slots) == 1
    assert len(queue._worker_tasks) == 1
    await queue.stop()
