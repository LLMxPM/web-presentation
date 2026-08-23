"""文件功能：为持久化页面任务 Worker 和续跑协调器提供不丢通知的进程内代次唤醒。"""

from __future__ import annotations

import asyncio


class GenerationWakeup:
    """使用递增代次配合 Condition，避免通知早于等待造成固定轮询空等。"""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._generation = 0

    @property
    def generation(self) -> int:
        """返回当前代次；调用方应在查询持久化状态前记录该值。"""

        return self._generation

    async def notify(self) -> None:
        """推进代次并唤醒当前进程内的全部等待者。"""

        async with self._condition:
            self._generation += 1
            self._condition.notify_all()

    async def wait(self, observed_generation: int, timeout: float) -> bool:
        """等待代次变化；超时返回 False，供数据库轮询继续兜底。"""

        async with self._condition:
            if self._generation != observed_generation:
                return True
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(
                        lambda: self._generation != observed_generation
                    ),
                    timeout=timeout,
                )
            except TimeoutError:
                return False
            return True


page_mutation_job_wakeup = GenerationWakeup()
page_mutation_batch_wakeup = GenerationWakeup()
