"""文件功能：验证页面持久化队列的代次唤醒不会丢通知，并保留轮询超时兜底。"""

from __future__ import annotations

import asyncio

import pytest

from app.ai.page_mutation_wakeup import GenerationWakeup


@pytest.mark.asyncio
async def test_notification_before_wait_should_be_observed_immediately() -> None:
    """查询期间到达的通知必须通过代次变化被等待者立即观察到。"""

    wakeup = GenerationWakeup()
    observed_generation = wakeup.generation
    await wakeup.notify()

    assert await wakeup.wait(observed_generation, timeout=1.0) is True


@pytest.mark.asyncio
async def test_notification_should_wake_all_current_waiters() -> None:
    """多个页面 Worker 等待同一代次时应全部被唤醒并重新竞争数据库任务。"""

    wakeup = GenerationWakeup()
    observed_generation = wakeup.generation
    waiters = [
        asyncio.create_task(wakeup.wait(observed_generation, timeout=1.0))
        for _ in range(3)
    ]
    await asyncio.sleep(0)
    await wakeup.notify()

    assert await asyncio.gather(*waiters) == [True, True, True]


@pytest.mark.asyncio
async def test_wait_timeout_should_preserve_database_polling_fallback() -> None:
    """没有本地通知时应按超时返回，让多实例和重启恢复继续查询数据库。"""

    wakeup = GenerationWakeup()

    assert await wakeup.wait(wakeup.generation, timeout=0.01) is False
