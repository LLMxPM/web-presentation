"""文件功能：登记普通 Run 的进程实例、续期心跳并对过期 owner 执行写围栏。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.run_write_fence import AgentRunWriteFenceLost
from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_process_owner import AiAgentProcessOwner
from app.services.durable_job_lease_service import build_durable_worker_id

_identity: tuple[int, str] | None = None


def get_agent_process_owner() -> str:
    """同一进程复用实例 UUID；fork/PID 改变后重新生成，避免 PID 重用误判。"""

    global _identity
    pid = os.getpid()
    if _identity is None or _identity[0] != pid:
        _identity = (pid, build_durable_worker_id())
    return _identity[1]


async def ensure_agent_process_owner(session: AsyncSession) -> str:
    """首次使用时登记 owner；已经过期的实例不能借新 Run 重新获得写权限。"""

    owner_id = get_agent_process_owner()
    now = utc_now()
    owner = await session.get(AiAgentProcessOwner, owner_id)
    if owner is None:
        session.add(AiAgentProcessOwner(
            owner_id=owner_id, heartbeat_at=now,
            expires_at=now + timedelta(seconds=get_settings().ai_run_owner_ttl_seconds),
        ))
        await session.flush()
    elif owner.expires_at <= now:
        raise AgentRunWriteFenceLost("AI 执行进程存活租约已失效，须重启进程。")
    return owner_id


async def heartbeat_agent_process(session: AsyncSession, *, owner_id: str, now: datetime) -> None:
    """仅续期尚未过期的具体实例；过期后拒绝复活，必须启用新的实例 UUID。"""

    result = await session.execute(update(AiAgentProcessOwner).where(
        AiAgentProcessOwner.owner_id == owner_id, AiAgentProcessOwner.expires_at > now,
    ).values(heartbeat_at=now, expires_at=now + timedelta(seconds=get_settings().ai_run_owner_ttl_seconds)))
    if result.rowcount != 1:
        raise AgentRunWriteFenceLost("AI 执行进程心跳已失效。")
    await session.commit()


@dataclass(frozen=True, slots=True)
class OrdinaryRunWriteFence:
    """把进程存活租约与 Run 归属传播到模型、工具及独立 Session 的事务提交。"""

    run_id: str
    owner_id: str

    def condition(self, now: datetime):
        """返回数据库围栏；不以模型事件频率判断存活。"""

        return exists(select(AiAgentProcessOwner.owner_id).where(
            AiAgentProcessOwner.owner_id == self.owner_id, AiAgentProcessOwner.expires_at > now,
        )) & exists(select(AiAgentRun.run_id).where(
            AiAgentRun.run_id == self.run_id, AiAgentRun.process_owner == self.owner_id,
        ))

    async def ensure_owned(self, session: AsyncSession, *, now: datetime) -> None:
        """先锁 owner 再确认 Run 归属，避免 autoflush 把失效结果提交到数据库。"""

        with session.no_autoflush:
            result = await session.execute(update(AiAgentProcessOwner).where(
                AiAgentProcessOwner.owner_id == self.owner_id, AiAgentProcessOwner.expires_at > now,
            ).values(heartbeat_at=AiAgentProcessOwner.heartbeat_at))
            if result.rowcount != 1 or not await self.is_owned(session, now=now):
                raise AgentRunWriteFenceLost("普通 AI Run 已失去进程写围栏。")

    async def is_owned(self, session: AsyncSession, *, now: datetime) -> bool:
        """只读检查实例租约和 Run 归属，避免在失效后创建新事件。"""

        with session.no_autoflush:
            return bool(await session.scalar(select(self.condition(now))))


async def bind_ordinary_run_owner(session: AsyncSession, run: AiAgentRun) -> OrdinaryRunWriteFence:
    """新执行/人工继续时 CAS 绑定实际 owner；自动外部续跑使用已有 Batch 围栏。"""

    owner_id = await ensure_agent_process_owner(session)
    result = await session.execute(update(AiAgentRun).where(
        AiAgentRun.run_id == run.run_id, AiAgentRun.status == run.status,
        AiAgentRun.process_owner == run.process_owner,
    ).values(process_owner=owner_id).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise AgentRunWriteFenceLost("AI Run 执行归属已变化。")
    run.process_owner = owner_id
    await session.commit()
    return OrdinaryRunWriteFence(run_id=run.run_id, owner_id=owner_id)
