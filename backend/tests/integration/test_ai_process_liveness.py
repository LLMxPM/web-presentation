"""文件功能：验证普通 Run 跨副本存活租约、终态 CAS、会话解除及迟到写入保护。"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import pytest
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.process_liveness import (
    OrdinaryRunWriteFence,
    bind_ordinary_run_owner,
    heartbeat_agent_process,
)
from app.ai.process_reaper import reap_expired_agent_runs
from app.ai.run_recovery import recover_interrupted_agent_runs_on_startup
from app.ai.run_write_fence import AgentRunWriteFenceLost
from app.core.time_utils import utc_now
from app.db.retry import run_with_write_retry
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentRunEvent
from app.models.ai_external_task import AiAgentExternalBatch
from app.models.ai_process_owner import AiAgentProcessOwner
from app.schemas.agent import AgentRunEvent
from sqlalchemy import func, select

from tests.integration.test_ai_run_stop_semantics import _seed_run


async def _owner(owner_id: str, *, expired: bool) -> None:
    """在隔离库登记指定实例；PID 可相同，失效只由具体 UUID 租约决定。"""

    now = utc_now()
    async with get_session_factory()() as session:
        session.add(AiAgentProcessOwner(
            owner_id=owner_id, heartbeat_at=now - timedelta(minutes=3),
            expires_at=now + timedelta(seconds=-1 if expired else 300),
        ))
        await session.commit()


async def test_reaper_handles_rebuilt_owner_and_protects_active_paused_and_external(authenticated_client):
    """hostname 改变/PID 重用不阻断收敛；活跃副本与暂停/外部等待继续存活。"""

    old = f"old-container:{os.getpid()}:old-instance"
    live = f"other-container:{os.getpid()}:live-instance"
    await _owner(old, expired=True)
    await _owner(live, expired=False)
    expected = {}
    for suffix, status, owner, terminal in (
        ("expired", "running", old, "failed"), ("cancel", "cancelling", old, "cancelled"),
        ("live", "running", live, "running"), ("paused", "paused", old, "paused"),
        ("external", "waiting_external", old, "waiting_external"),
    ):
        _, _, run_id = await _seed_run(authenticated_client, suffix=suffix, status=status, process_owner=owner)
        expected[run_id] = terminal
    async with get_session_factory()() as session:
        assert await reap_expired_agent_runs(session) == 2
        for run_id, terminal in expected.items():
            run = await session.get(AiAgentRun, run_id)
            assert run.status == terminal
            if terminal == "failed":
                assert run.error_code == "AI_RUN_PROCESS_STOPPED"


async def test_reaper_does_not_interrupt_external_batch_handoff(authenticated_client):
    """外部 Batch 已持有续跑交接，即使父 Run 仍 running 也不能由普通收敛器接管。"""

    owner = "old:1:batch-owner"
    await _owner(owner, expired=True)
    _, session_id, run_id = await _seed_run(authenticated_client, suffix="batch", status="running", process_owner=owner)
    async with get_session_factory()() as session:
        session.add(AiAgentExternalBatch(
            batch_id="protected", run_id=run_id, session_id=session_id, sequence_no=1,
            status="resuming", worker_id="coordinator-b", lease_expires_at=utc_now() + timedelta(minutes=1),
        ))
        await session.commit()
        assert await reap_expired_agent_runs(session) == 0
        assert (await session.get(AiAgentRun, run_id)).status == "running"


async def test_concurrent_reapers_close_once_and_release_session(authenticated_client):
    """双收敛者使用真实独立 Session，终态/事件仅一次，active 唯一占用释放。"""

    owner = "gone:7:uuid"
    await _owner(owner, expired=True)
    _, session_id, run_id = await _seed_run(authenticated_client, suffix="race", status="running", process_owner=owner)
    factory = get_session_factory()
    results = await asyncio.gather(*(
        run_with_write_retry(reap_expired_agent_runs, session_factory=factory, backoff_delays=(0.05, 0.1))
        for _ in range(2)
    ))
    assert sum(results) == 1
    async with factory() as session:
        run = await session.get(AiAgentRun, run_id)
        assert run.process_owner is None
        assert await session.scalar(select(func.count()).select_from(AiAgentRunEvent).where(
            AiAgentRunEvent.run_id == run_id, AiAgentRunEvent.event == "run.error",
        )) == 1
        await PlatformAgentRuntimeStore(session, user_id=run.user_id).ensure_no_active_run(
            session_id=session_id, agent_id="agent-coordinator",
        )


async def test_expired_instance_cannot_renew_or_write_late_results(authenticated_client):
    """过期实例无法复活；旧工具/事件的事务提交围栏失败，数据库不留迟到事件。"""

    owner = "expired:2:uuid"
    await _owner(owner, expired=True)
    _, _, run_id = await _seed_run(authenticated_client, suffix="late", status="running", process_owner=owner)
    async with get_session_factory()() as session:
        with pytest.raises(AgentRunWriteFenceLost):
            await heartbeat_agent_process(session, owner_id=owner, now=utc_now())
        await session.rollback()
        run = await session.get(AiAgentRun, run_id)
        store = PlatformAgentRuntimeStore(session, user_id=run.user_id, write_fence=OrdinaryRunWriteFence(run_id, owner))
        with pytest.raises(AgentRunWriteFenceLost):
            await store.append_event(run, AgentRunEvent(event="run.message.delta", content="迟到"))
        await session.rollback()
        assert await session.scalar(select(func.count()).select_from(AiAgentRunEvent).where(
            AiAgentRunEvent.run_id == run_id,
        )) == 0


async def test_registered_live_owner_overrides_local_pid_probe(authenticated_client, monkeypatch):
    """相同 hostname/PID namespace 探测错误时，登记心跳优先，启动恢复不误杀。"""

    owner = "same-host:9999:live"
    await _owner(owner, expired=False)
    _, _, run_id = await _seed_run(authenticated_client, suffix="namespace", status="running", process_owner=owner)
    monkeypatch.setattr("app.ai.run_recovery.process_is_alive", lambda _: False)
    assert await recover_interrupted_agent_runs_on_startup(get_session_factory(), local_hostname="same-host") == 0
    async with get_session_factory()() as session:
        assert (await session.get(AiAgentRun, run_id)).status == "running"


async def test_manual_continue_rebinds_actual_process_owner(authenticated_client):
    """暂停 Run 可以由新进程人工继续，归属更新后旧实例围栏不能写入。"""

    owner = "previous:3:uuid"
    await _owner(owner, expired=False)
    _, _, run_id = await _seed_run(authenticated_client, suffix="rebind", status="paused", process_owner=owner)
    async with get_session_factory()() as session:
        run = await session.get(AiAgentRun, run_id)
        fence = await bind_ordinary_run_owner(session, run)
        assert fence.owner_id != owner
        assert await fence.is_owned(session, now=utc_now())
        assert not await OrdinaryRunWriteFence(run_id, owner).is_owned(session, now=utc_now())
