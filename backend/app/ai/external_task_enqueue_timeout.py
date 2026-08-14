"""文件功能：为外部任务入队阶段提供统一的短超时与可恢复错误契约。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from time import monotonic
from typing import TypeVar

from app.core.config import get_settings
from app.core.exceptions import AppException


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ExternalTaskEnqueueDeadline:
    """在工具上下文解析与任务提交之间共享同一个短入队期限。"""

    expires_at: float

    @classmethod
    def start(cls) -> "ExternalTaskEnqueueDeadline":
        """按当前配置创建从工具准备阶段开始计时的入队期限。"""

        timeout_seconds = float(get_settings().ai_external_task_enqueue_timeout_seconds)
        return cls(expires_at=monotonic() + timeout_seconds)

    async def wait(self, awaitable: Awaitable[T]) -> T:
        """等待当前入队步骤，但所有步骤合计不得超过共享期限。"""

        try:
            async with asyncio.timeout(max(0.0, self.expires_at - monotonic())):
                return await awaitable
        except TimeoutError as exc:
            raise AppException(
                status_code=503,
                code="AI_EXTERNAL_TASK_ENQUEUE_TIMEOUT",
                detail="后台任务准备或入队超时，当前操作是否已登记暂时无法确认。",
                data={
                    "retryable": True,
                    "outcome": "unknown",
                    "hint": "先查询目标实体的最新状态；确认操作未生效后，再使用最新版本参数重新调用。",
                },
            ) from exc


async def wait_for_external_task_enqueue(awaitable: Awaitable[T]) -> T:
    """为仅含单一步骤的外部任务入队提供便捷短超时。"""

    return await ExternalTaskEnqueueDeadline.start().wait(awaitable)
