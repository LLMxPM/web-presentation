"""文件功能：为后台 AI 外部任务续跑提供与运行态写入同事务的租约围栏。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Protocol, runtime_checkable

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_external_task import AiAgentExternalBatch
from app.models.ai_agent_runtime import AiAgentRun


class AgentRunWriteFenceLost(RuntimeError):
    """表示后台续跑已不再拥有 Batch 租约，调用方必须回滚本次运行态写入。"""


@runtime_checkable
class AgentRunWriteFence(Protocol):
    """约束后台 Agent 执行期间所有数据库写入必须满足的租约接口。"""

    def condition(self, now: datetime) -> Any:
        """返回可附加到条件写语句的数据库表达式。"""

    async def ensure_owned(self, session: AsyncSession, *, now: datetime) -> None:
        """在当前事务内锁定并确认调用方仍拥有写权限。"""

    async def is_owned(self, session: AsyncSession, *, now: datetime) -> bool:
        """只读检查当前调用方是否仍拥有写权限。"""


_CURRENT_AGENT_RUN_WRITE_FENCE: ContextVar[AgentRunWriteFence | None] = ContextVar(
    "current_agent_run_write_fence",
    default=None,
)


def current_agent_run_write_fence() -> AgentRunWriteFence | None:
    """读取当前异步执行上下文绑定的 Agent 写围栏。"""

    return _CURRENT_AGENT_RUN_WRITE_FENCE.get()


@contextmanager
def agent_run_write_fence_scope(write_fence: AgentRunWriteFence | None) -> Iterator[None]:
    """在当前异步调用链中传播写围栏；空值保持外层已有围栏。"""

    if write_fence is None:
        yield
        return
    token = _CURRENT_AGENT_RUN_WRITE_FENCE.set(write_fence)
    try:
        yield
    finally:
        _CURRENT_AGENT_RUN_WRITE_FENCE.reset(token)


@dataclass(frozen=True, slots=True)
class ExternalBatchContinuationWriteFence:
    """约束统一外部Batch续跑的所有运行态写入必须由当前租约代次完成。"""

    batch_id: str
    worker_id: str
    lease_generation: int

    def lease_conditions(self, now: datetime) -> tuple[Any, ...]:
        """返回不含Run状态的租约条件，供协调器在Run终态后执行Batch收尾。"""

        return (
            AiAgentExternalBatch.batch_id == self.batch_id,
            AiAgentExternalBatch.status == "resuming",
            AiAgentExternalBatch.worker_id == self.worker_id,
            AiAgentExternalBatch.lease_generation == self.lease_generation,
            AiAgentExternalBatch.lease_expires_at.is_not(None),
            AiAgentExternalBatch.lease_expires_at > now,
        )

    def batch_conditions(self, now: datetime) -> tuple[Any, ...]:
        """返回统一Batch租约及Run写权限条件。"""

        return (
            *self.lease_conditions(now),
            exists(
                select(AiAgentRun.run_id).where(
                    AiAgentRun.run_id == AiAgentExternalBatch.run_id,
                    AiAgentRun.status.in_(("running", "paused", "waiting_external", "completed")),
                    AiAgentRun.cancel_requested_at.is_(None),
                )
            ),
        )

    def condition(self, now: datetime) -> Any:
        """构造可嵌入其它写语句的统一Batch EXISTS围栏。"""

        return exists(select(AiAgentExternalBatch.batch_id).where(*self.batch_conditions(now)))

    async def ensure_owned(self, session: AsyncSession, *, now: datetime) -> None:
        """在提交前锁定并确认当前续跑租约。"""

        result = await session.execute(
            update(AiAgentExternalBatch)
            .where(*self.batch_conditions(now))
            .values(lease_generation=AiAgentExternalBatch.lease_generation)
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) != 1:
            raise AgentRunWriteFenceLost(
                f"AI外部Batch续跑租约已失效：batch={self.batch_id}, generation={self.lease_generation}"
            )

    async def is_owned(self, session: AsyncSession, *, now: datetime) -> bool:
        """只读检查统一Batch租约所有权。"""

        return await session.scalar(select(AiAgentExternalBatch.batch_id).where(*self.batch_conditions(now))) is not None
