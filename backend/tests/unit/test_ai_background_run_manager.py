"""文件功能：验证进程内智能体后台任务的会话互斥、取消和阶段衔接。"""

from __future__ import annotations

import asyncio

import pytest

from app.ai.background_run_manager import AgentBackgroundRunManager


@pytest.mark.asyncio
async def test_background_run_should_continue_without_subscriber() -> None:
    """后台任务的完成只依赖执行器，不依赖任何 SSE 消费者。"""

    manager = AgentBackgroundRunManager()
    release = asyncio.Event()
    completed = asyncio.Event()

    async def worker() -> None:
        await release.wait()
        completed.set()

    await manager.start(
        run_id="run-1",
        session_id="session-1",
        agent_id="agent-coordinator",
        worker_factory=worker,
    )
    release.set()
    await manager.wait("run-1")

    assert completed.is_set()
    await manager.shutdown()


@pytest.mark.asyncio
async def test_background_run_should_reject_other_run_in_same_session() -> None:
    """同一会话已有后台阶段时不得启动另一个 run。"""

    manager = AgentBackgroundRunManager()
    release = asyncio.Event()

    async def worker() -> None:
        await release.wait()

    await manager.start(
        run_id="run-1",
        session_id="session-1",
        agent_id="agent-coordinator",
        worker_factory=worker,
    )
    with pytest.raises(ValueError, match="AI_SESSION_RUN_ACTIVE"):
        await manager.start(
            run_id="run-2",
            session_id="session-1",
            agent_id="agent-coordinator",
            worker_factory=worker,
        )

    release.set()
    await manager.wait("run-1")
    await manager.shutdown()


@pytest.mark.asyncio
async def test_background_run_cancel_should_cancel_owned_task() -> None:
    """强制取消应真正取消当前进程持有的执行任务。"""

    manager = AgentBackgroundRunManager()
    cancelled = asyncio.Event()

    async def worker() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    await manager.start(
        run_id="run-1",
        session_id="session-1",
        agent_id="agent-coordinator",
        worker_factory=worker,
    )
    await asyncio.sleep(0)

    assert await manager.cancel("run-1") is True
    assert cancelled.is_set()
    assert await manager.cancel("run-1") is False
    await manager.shutdown()
