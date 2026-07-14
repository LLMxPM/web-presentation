"""文件功能：为后台 AI 页面变更续跑提供与运行态写入同事务的租约围栏。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_page_mutation import AiPageMutationBatch


class AgentRunWriteFenceLost(RuntimeError):
    """表示后台续跑已不再拥有 Batch 租约，调用方必须回滚本次运行态写入。"""


@dataclass(frozen=True, slots=True)
class PageMutationContinuationWriteFence:
    """描述一次 Batch 续跑的不可复用租约代次。"""

    batch_id: str
    worker_id: str
    lease_generation: int

    def batch_conditions(self, now: datetime) -> tuple[Any, ...]:
        """返回直接约束 Batch 行的条件，供续租和提交前确认复用。"""

        return (
            AiPageMutationBatch.batch_id == self.batch_id,
            AiPageMutationBatch.status == "resuming",
            AiPageMutationBatch.worker_id == self.worker_id,
            AiPageMutationBatch.lease_generation == self.lease_generation,
            AiPageMutationBatch.lease_expires_at.is_not(None),
            AiPageMutationBatch.lease_expires_at > now,
        )

    def condition(self, now: datetime) -> Any:
        """构造可嵌入其它 UPDATE 的 EXISTS 围栏条件，避免额外提交写入。"""

        return exists(
            select(AiPageMutationBatch.batch_id).where(*self.batch_conditions(now))
        )

    async def ensure_owned(self, session: AsyncSession, *, now: datetime) -> None:
        """在当前事务内确认围栏仍有效；失败时调用方提交会被阻止并应回滚。"""

        result = await session.execute(
            update(AiPageMutationBatch)
            .where(*self.batch_conditions(now))
            # 保持字段值不变，仅借同一事务中的条件 UPDATE 建立提交前栅栏。
            .values(lease_generation=AiPageMutationBatch.lease_generation)
            .execution_options(synchronize_session=False)
        )
        if int(result.rowcount or 0) != 1:
            raise AgentRunWriteFenceLost(
                f"AI 页面变更续跑租约已失效：batch={self.batch_id}, generation={self.lease_generation}"
            )

    async def is_owned(self, session: AsyncSession, *, now: datetime) -> bool:
        """只读确认当前围栏是否仍属于调用方，用于解释条件写失败原因。"""

        return (
            await session.scalar(select(AiPageMutationBatch.batch_id).where(*self.batch_conditions(now)))
        ) is not None
