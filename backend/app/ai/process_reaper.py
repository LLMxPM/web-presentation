"""文件功能：独立于 SSE 续期进程心跳、收敛已失效 owner 的普通 Run。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.background_run_manager import AgentBackgroundRunManager
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.process_liveness import get_agent_process_owner, heartbeat_agent_process
from app.ai.run_write_fence import AgentRunWriteFenceLost
from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_external_task import AiAgentExternalBatch
from app.models.ai_process_owner import AiAgentProcessOwner
from app.services.durable_job_lease_service import claim_rows_by_cas

logger = logging.getLogger(__name__)


def _ordinary_run_conditions(now: datetime):
    """只处理普通执行；整个未完成外部 Batch 交接窗口交给原协调器收敛。"""

    return (
        AiAgentRun.status.in_(("pending", "running", "cancelling")),
        exists(select(AiAgentProcessOwner.owner_id).where(
            AiAgentProcessOwner.owner_id == AiAgentRun.process_owner,
            AiAgentProcessOwner.expires_at <= now,
        )),
        ~exists(select(AiAgentExternalBatch.batch_id).where(
            AiAgentExternalBatch.run_id == AiAgentRun.run_id,
            AiAgentExternalBatch.status.in_(("collecting", "waiting", "ready", "resuming")),
        )),
    )


async def reap_expired_agent_runs(
    session: AsyncSession, *, now: datetime | None = None,
) -> int:
    """借统一 CAS 时序移除失效 owner 并同事务写终态，双收敛者只命中一次。"""

    anchor = now or utc_now()
    conditions = _ordinary_run_conditions(anchor)
    query = select(
        AiAgentRun.run_id, AiAgentRun.process_owner, AiAgentRun.status, AiAgentRun.cancel_requested_at,
    ).where(*conditions).order_by(AiAgentRun.started_at, AiAgentRun.run_id)

    def claim(row):
        """复核候选 owner、状态、取消快照与外部交接，不能覆盖新的执行。"""

        return update(AiAgentRun).where(
            AiAgentRun.run_id == row.run_id, AiAgentRun.process_owner == row.process_owner,
            AiAgentRun.status == row.status, AiAgentRun.cancel_requested_at == row.cancel_requested_at,
            *conditions,
        ).values(process_owner=None).execution_options(synchronize_session=False)

    async def finish(row):
        """在 CAS 持锁事务中释放 active 唯一占用并保存事件与工具/requirement 终态。"""

        run = await session.get(AiAgentRun, row.run_id, populate_existing=True)
        store = PlatformAgentRuntimeStore(session, user_id=run.user_id)
        if row.status == "cancelling" or row.cancel_requested_at is not None:
            await store.mark_terminal(run, status="cancelled", content="执行进程已停止，取消已完成。", commit=False)
        else:
            await store.mark_terminal(
                run, status="failed", error_code="AI_RUN_PROCESS_STOPPED",
                error_message="执行进程存活租约已失效，请重新发起运行。", commit=False,
            )

    rows = await claim_rows_by_cas(
        session, AiAgentRun, candidate_query=query, candidate_limit=100,
        claim_cas=claim, validate_claimed=finish,
    )
    return len(rows)


async def run_agent_process_monitor(
    factory: async_sessionmaker[AsyncSession], manager: AgentBackgroundRunManager,
) -> None:
    """分别调度心跳与收敛；失去自身租约时停止接收/执行普通 Run，收敛仍继续。"""

    async def heartbeat_loop():
        """心跳不依赖模型事件；过期后不允许复活相同实例。"""

        while True:
            try:
                async def renew(session):
                    """每次重试重新取时，避免数据库写冲突延长已过期的存活租约。"""

                    await heartbeat_agent_process(session, owner_id=get_agent_process_owner(), now=utc_now())

                await run_with_write_retry(renew, session_factory=factory, backoff_delays=(0.05, 0.1))
            except AgentRunWriteFenceLost:
                logger.error("AI 进程存活租约失效，停止普通 Run 执行。")
                await manager.shutdown()
                return
            except Exception:
                logger.exception("AI 进程心跳更新失败。")
            await asyncio.sleep(get_settings().ai_run_owner_heartbeat_seconds)

    async def reaper_loop():
        """各副本可同时扫描，通过统一 CAS 防止重复终态与误收活跃 owner。"""

        while True:
            try:
                await run_with_write_retry(
                    reap_expired_agent_runs, session_factory=factory, backoff_delays=(0.05, 0.1),
                )
            except Exception:
                logger.exception("AI 失效 owner 收敛失败。")
            await asyncio.sleep(get_settings().ai_run_owner_sweep_seconds)

    await asyncio.gather(heartbeat_loop(), reaper_loop())
