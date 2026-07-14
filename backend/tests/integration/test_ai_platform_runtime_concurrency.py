"""文件功能：验证平台 AI 运行事件在 SQLite 多会话并发与写锁场景下的事务安全性。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

import app.ai.platform_runtime as platform_runtime
from app.ai.platform_runtime import PlatformAgentRuntimeStore, get_live_run_activity_version
from app.ai.run_event_writer import allocate_run_event_index
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentRunEvent
from app.schemas.agent import AgentRunEvent, AgentScopeContext


async def _create_runtime_run(
    authenticated_client: AsyncClient,
    *,
    run_id: str,
) -> tuple[str, AgentScopeContext]:
    """创建并启动测试 run，返回会话 ID 与业务范围。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": f"并发运行态-{run_id}", "status": "active"},
    )
    assert workspace_response.status_code == 200
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_response.json()["id"],
        source="editor-component-library",
    )
    session_id = f"session-{run_id}"
    async with get_session_factory()() as setup_session:
        store = PlatformAgentRuntimeStore(setup_session, user_id=1)
        await store.create_session(
            session_id=session_id,
            agent_id="component-manager",
            session_name="并发事件测试会话",
            scope=scope,
        )
        await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id=run_id,
            message="开始并发事件任务",
            image_attachment_ids=[],
        )
    return session_id, scope


async def _allocate_and_commit(session: AsyncSession, *, run_id: str) -> int:
    """在独立会话中直接分配游标并提交，用于绕过进程内事件写锁验证数据库原子性。"""

    event_index = await allocate_run_event_index(
        session,
        run_id=run_id,
        updated_at=datetime.now(UTC),
    )
    await session.commit()
    return event_index


async def test_atomic_allocator_should_return_unique_indexes_across_sqlite_sessions(
    authenticated_client: AsyncClient,
) -> None:
    """不同 AsyncSession 直接并发分配同一游标时，数据库应返回连续唯一值。"""

    run_id = "platform-runtime-run-db-atomic-cursor"
    await _create_runtime_run(authenticated_client, run_id=run_id)
    session_factory = get_session_factory()
    writer_sessions = [session_factory() for _ in range(12)]
    try:
        allocated_indexes = await asyncio.gather(
            *(
                _allocate_and_commit(session, run_id=run_id)
                for session in writer_sessions
            )
        )
    finally:
        await asyncio.gather(*(session.close() for session in writer_sessions))

    async with session_factory() as verify_session:
        persisted_index = await verify_session.scalar(
            select(AiAgentRun.event_index).where(AiAgentRun.run_id == run_id)
        )

    assert sorted(allocated_indexes) == list(range(1, 13))
    assert persisted_index == 12


async def test_append_event_should_persist_unique_indexes_from_concurrent_sqlite_sessions(
    authenticated_client: AsyncClient,
) -> None:
    """多个真实 SQLite 会话并发追加同一 run 时，事件行游标应连续且唯一。"""

    run_id = "platform-runtime-run-concurrent-events"
    session_id, _ = await _create_runtime_run(authenticated_client, run_id=run_id)
    session_factory = get_session_factory()
    writer_sessions = [session_factory() for _ in range(12)]
    try:
        stores = [PlatformAgentRuntimeStore(session, user_id=1) for session in writer_sessions]
        run_models = await asyncio.gather(
            *(
                store.get_active_run_model(
                    session_id=session_id,
                    agent_id="component-manager",
                )
                for store in stores
            )
        )
        assert all(run_model is not None for run_model in run_models)
        stored_events = await asyncio.gather(
            *(
                store.append_event(
                    run_model,
                    AgentRunEvent(
                        event="message.delta",
                        run_id=run_id,
                        session_id=session_id,
                        content=f"[{index}]",
                    ),
                )
                for index, (store, run_model) in enumerate(zip(stores, run_models, strict=True))
                if run_model is not None
            )
        )
    finally:
        await asyncio.gather(*(session.close() for session in writer_sessions))

    async with session_factory() as verify_session:
        event_indexes = (
            await verify_session.execute(
                select(AiAgentRunEvent.event_index)
                .where(AiAgentRunEvent.run_id == run_id)
                .order_by(AiAgentRunEvent.event_index.asc())
            )
        ).scalars().all()
        persisted_run = await verify_session.get(AiAgentRun, run_id)

    assert sorted(event.event_index for event in stored_events if event.event_index is not None) == list(range(1, 13))
    assert event_indexes == list(range(13))
    assert persisted_run is not None
    assert persisted_run.event_index == 12
    assert len(persisted_run.content or "") == len("[0]") * 10 + len("[10]") * 2


async def test_append_event_should_retry_clean_sqlite_transaction_after_lock(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """纯事件追加遇 SQLite 写锁时，应 rollback 后有限重试且保留最新聚合内容。"""

    run_id = "platform-runtime-run-sqlite-lock-retry"
    session_id, _ = await _create_runtime_run(authenticated_client, run_id=run_id)

    async with get_session_factory()() as writer_session, get_session_factory()() as blocker_session:
        await writer_session.execute(text("PRAGMA busy_timeout=1"))
        writer_store = PlatformAgentRuntimeStore(writer_session, user_id=1)
        writer_run = await writer_store.get_active_run_model(
            session_id=session_id,
            agent_id="component-manager",
        )
        assert writer_run is not None
        await blocker_session.execute(
            update(AiAgentRun)
            .where(AiAgentRun.run_id == run_id)
            .values(content="锁持有期间的内容。")
        )
        rollback_count = 0
        original_rollback = writer_session.rollback

        async def tracked_rollback() -> None:
            """记录锁冲突后的事务恢复次数。"""

            nonlocal rollback_count
            rollback_count += 1
            await original_rollback()

        monkeypatch.setattr(writer_session, "rollback", tracked_rollback)

        async def release_blocker() -> None:
            """短暂持有 SQLite 写锁，使事件追加稳定触发 BUSY。"""

            await asyncio.sleep(0.04)
            await blocker_session.commit()

        release_task = asyncio.create_task(release_blocker())
        stored_event = await writer_store.append_event(
            writer_run,
            AgentRunEvent(
                event="message.delta",
                run_id=run_id,
                session_id=session_id,
                content="事件追加。",
            ),
        )
        await release_task

        rollback_count_before_exhaustion = rollback_count
        monkeypatch.setattr(platform_runtime, "_SQLITE_EVENT_WRITE_MAX_ATTEMPTS", 2)
        await blocker_session.execute(
            update(AiAgentRun)
            .where(AiAgentRun.run_id == run_id)
            .values(reasoning_content="持续持有写锁。")
        )
        with pytest.raises(OperationalError):
            await writer_store.append_event(
                writer_run,
                AgentRunEvent(
                    event="reasoning.delta",
                    run_id=run_id,
                    session_id=session_id,
                    content="不应写入。",
                ),
            )
        await blocker_session.rollback()

    async with get_session_factory()() as verify_session:
        persisted_run = await verify_session.get(AiAgentRun, run_id)

    assert rollback_count >= 1
    assert rollback_count == rollback_count_before_exhaustion + 2
    assert stored_event.event_index == 1
    assert persisted_run is not None
    assert persisted_run.content == "锁持有期间的内容。事件追加。"


async def test_append_event_should_avoid_process_lock_after_sqlite_write(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会话已持有 SQLite 写锁时应直接续写，避免与等待数据库锁的任务形成锁序反转。"""

    run_id = "platform-runtime-run-existing-write-transaction"
    session_id, _ = await _create_runtime_run(authenticated_client, run_id=run_id)
    async with get_session_factory()() as writer_session:
        store = PlatformAgentRuntimeStore(writer_session, user_id=1)
        run_model = await writer_session.get(AiAgentRun, run_id)
        assert run_model is not None
        await writer_session.execute(
            update(AiAgentRun)
            .where(AiAgentRun.run_id == run_id)
            .values(reasoning_content="同事务预写入。")
        )

        def fail_if_process_lock_is_requested(_: str) -> asyncio.Lock:
            """已有 SQLite 写事务时不应再进入进程锁。"""

            raise AssertionError("不应在持有 SQLite 写锁后申请进程级 run 锁")

        monkeypatch.setattr(platform_runtime, "_get_run_event_lock", fail_if_process_lock_is_requested)
        stored_event = await store.append_event(
            run_model,
            AgentRunEvent(
                event="message.delta",
                run_id=run_id,
                session_id=session_id,
                content="事件已写入。",
            ),
        )

    assert stored_event.event_index == 1


async def test_member_event_should_not_append_after_parent_run_terminal(
    authenticated_client: AsyncClient,
) -> None:
    """父 run 已终止后，成员事件不得递增游标或写入事件表。"""

    run_id = "platform-runtime-run-terminal-member-event"
    session_id, _ = await _create_runtime_run(authenticated_client, run_id=run_id)
    active_version = get_live_run_activity_version(run_id)
    session_factory = get_session_factory()
    async with session_factory() as terminal_session:
        terminal_store = PlatformAgentRuntimeStore(terminal_session, user_id=1)
        run_model = await terminal_session.get(AiAgentRun, run_id)
        assert run_model is not None
        terminal_event = await terminal_store.mark_terminal(run_model, status="completed", content="任务完成。")

    async with session_factory() as member_session:
        member_store = PlatformAgentRuntimeStore(member_session, user_id=1)
        terminal_run = await member_session.get(AiAgentRun, run_id)
        assert terminal_run is not None
        with pytest.raises(ValueError, match="AI_RUN_TERMINAL"):
            await member_store.append_event(
                terminal_run,
                AgentRunEvent(
                    event="member.message.delta",
                    run_id=run_id,
                    session_id=session_id,
                    content="迟到的成员输出。",
                ),
            )

    async with session_factory() as verify_session:
        persisted_index = await verify_session.scalar(
            select(AiAgentRun.event_index).where(AiAgentRun.run_id == run_id)
        )
        member_event_count = await verify_session.scalar(
            select(func.count(AiAgentRunEvent.id)).where(
                AiAgentRunEvent.run_id == run_id,
                AiAgentRunEvent.event.like("member.%"),
            )
        )

    assert terminal_event.event_index == 1
    assert persisted_index == 1
    assert member_event_count == 0
    assert active_version > 0
    assert get_live_run_activity_version(run_id) == 0
