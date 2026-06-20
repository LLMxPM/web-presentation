"""文件功能：验证 Pydantic AI 切换后的平台自有智能体运行态闭环。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, ToolReturnPart, UserPromptPart
from sqlalchemy import select

import app.ai.platform_runtime as platform_runtime
from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.message_history import build_context_limit_processor, build_history_budget, rebuild_agent_message_history
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.pydantic_runner import PydanticAgentRunner
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentRunEvent, AiAgentSession, AiAgentToolCall
from app.schemas.agent import AgentRunEvent, AgentScopeContext


async def test_platform_runtime_should_persist_events_messages_and_snapshot(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """平台运行态应能保存 run、工具事件、消息，并恢复 runtime snapshot。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        flush_calls: list[list[object] | None] = []
        original_flush = db_session.flush

        async def tracked_flush(objects: object | None = None, *args: object, **kwargs: object) -> None:
            """记录 flush 顺序，确保 run 父记录先于消息子记录写入。"""

            flush_calls.append(None if objects is None else list(objects))
            await original_flush(objects, *args, **kwargs)

        monkeypatch.setattr(db_session, "flush", tracked_flush)
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-1",
            message="整理组件库",
            image_attachment_ids=[],
        )
        run_model = run_start.run_model
        assert flush_calls[0] is not None
        assert isinstance(flush_calls[0][0], AiAgentRun)
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="reasoning.delta",
                run_id=run_model.run_id,
                session_id=session_id,
                content="先读取组件概览。",
            ),
        )
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="message.delta",
                run_id=run_model.run_id,
                session_id=session_id,
                content="正在整理组件库。",
            ),
        )
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.started",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "list_workspace_components",
                    "tool_call_id": "tool-call-1",
                    "tool_args": {"workspace_id": workspace_id},
                },
            ),
        )
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.completed",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "list_workspace_components",
                    "tool_call_id": "tool-call-1",
                    "result": {"total": 2},
                },
            ),
        )
        active_snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=AgentRuntimeContext(
                scope_type=scope.scope_type,
                workspace_id=workspace_id,
                source=scope.source,
            ),
        )
        await store.append_assistant_message(
            run_model,
            content="组件库整理完成。",
            reasoning_content="先读取组件概览。",
            message_history=[{"kind": "summary"}],
        )
        await store.mark_terminal(run_model, status="completed", content="组件库整理完成。")
        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=AgentRuntimeContext(
                scope_type=scope.scope_type,
                workspace_id=workspace_id,
                source=scope.source,
            ),
        )
        messages = await store.list_messages(session_id=session_id, agent_id="component-manager")

    assert [item.role for item in messages] == ["user", "assistant"]
    assert messages[0].content == "整理组件库"
    assert messages[1].reasoning_content == "先读取组件概览。"
    assert active_snapshot.active_run is not None
    assert active_snapshot.active_run.status == "running"
    assert [item.kind for item in active_snapshot.timeline_items] == ["message", "reasoning", "message", "tool"]
    assert active_snapshot.timeline_items[1].content == "先读取组件概览。"
    assert active_snapshot.timeline_items[2].content == "正在整理组件库。"
    assert snapshot.last_run is not None
    assert snapshot.last_run.status == "completed"
    assert [item.kind for item in snapshot.timeline_items] == ["message", "reasoning", "message", "tool"]
    assert snapshot.timeline_items[-1].tool is not None
    assert snapshot.timeline_items[-1].tool.output_payload == {"total": 2}


async def test_platform_runtime_should_refresh_event_cursor_before_append(
    authenticated_client: AsyncClient,
) -> None:
    """停止请求与流式事件使用不同 DB 会话时，应按最新游标继续追加事件。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态并发游标工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态并发游标会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as first_session:
        first_store = PlatformAgentRuntimeStore(first_session, user_id=1)
        run_start = await first_store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-cursor",
            message="开始长任务",
            image_attachment_ids=[],
        )
        stale_run_model = run_start.run_model
        assert stale_run_model.event_index == 0

        async with get_session_factory()() as second_session:
            second_store = PlatformAgentRuntimeStore(second_session, user_id=1)
            fresh_run_model = await second_store.get_active_run_model(
                session_id=session_id,
                agent_id="component-manager",
            )
            assert fresh_run_model is not None
            await second_store.append_event(
                fresh_run_model,
                AgentRunEvent(
                    event="message.delta",
                    run_id=fresh_run_model.run_id,
                    session_id=session_id,
                    content="流式输出。",
                ),
            )

        cancel_event = await first_store.append_event(
            stale_run_model,
            AgentRunEvent(
                event="run.cancelling",
                run_id=stale_run_model.run_id,
                session_id=session_id,
                data={"message": "正在停止当前运行。"},
            ),
        )

        assert cancel_event.event_index == 2
        result = await first_session.execute(
            select(AiAgentRunEvent.event_index)
            .where(AiAgentRunEvent.run_id == stale_run_model.run_id)
            .order_by(AiAgentRunEvent.event_index.asc())
        )
        assert result.scalars().all() == [0, 1, 2]


async def test_platform_runtime_stream_should_poll_database_when_subscriber_misses_event(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件流订阅未收到本进程通知时，应通过 PostgreSQL 轮询恢复新事件。"""

    subscribed = asyncio.Event()

    def fake_subscribe(run_id: str) -> asyncio.Queue:
        """返回未注册队列，模拟跨进程或漏通知的恢复场景。"""

        _ = run_id
        subscribed.set()
        return asyncio.Queue()

    monkeypatch.setattr(platform_runtime, "_subscribe", fake_subscribe)
    monkeypatch.setattr(platform_runtime, "_EVENT_POLL_INTERVAL_SECONDS", 0.01)

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态轮询恢复工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态轮询恢复会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as stream_session:
        stream_store = PlatformAgentRuntimeStore(stream_session, user_id=1)
        run_start = await stream_store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-polling-stream",
            message="开始后台任务",
            image_attachment_ids=[],
        )
        stream = platform_runtime.stream_replay_then_subscribe(
            store=stream_store,
            run_id=run_start.run_model.run_id,
            event_index=run_start.run_model.event_index,
        )
        next_event_task = asyncio.create_task(_read_next_sse_event(stream))
        await asyncio.wait_for(subscribed.wait(), timeout=1)

        async with get_session_factory()() as writer_session:
            writer_store = PlatformAgentRuntimeStore(writer_session, user_id=1)
            writer_run = await writer_store.get_active_run_model(
                session_id=session_id,
                agent_id="component-manager",
            )
            assert writer_run is not None
            await writer_store.append_event(
                writer_run,
                AgentRunEvent(
                    event="message.delta",
                    run_id=writer_run.run_id,
                    session_id=session_id,
                    content="后台轮询恢复输出。",
                ),
            )

        event = await asyncio.wait_for(next_event_task, timeout=1)
        await stream.aclose()

    assert event.event == "message.delta"
    assert event.content == "后台轮询恢复输出。"


async def test_platform_runtime_should_fill_tool_input_when_complete_args_arrive_late(
    authenticated_client: AsyncClient,
) -> None:
    """同一工具调用先收到空 args 后收到完整 args 时，应更新工具详情和回放 timeline。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态工具参数补全工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态工具参数补全会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-late-tool-args",
            message="需要提问",
            image_attachment_ids=[],
        )
        run_model = run_start.run_model
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.started",
                run_id=run_model.run_id,
                session_id=session_id,
                data={"tool_name": "ask_user", "tool_call_id": "tool-ask-1", "tool_args": ""},
            ),
        )
        full_args = {"questions": [{"question": "需要采用哪种布局？", "options": [{"label": "紧凑"}]}]}
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.started",
                run_id=run_model.run_id,
                session_id=session_id,
                data={"tool_name": "ask_user", "tool_call_id": "tool-ask-1", "tool_args": full_args},
            ),
        )
        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=AgentRuntimeContext(
                scope_type=scope.scope_type,
                workspace_id=workspace_id,
                source=scope.source,
            ),
        )
        tool_input = await db_session.scalar(
            select(AiAgentToolCall.input_payload_json).where(
                AiAgentToolCall.run_id == run_model.run_id,
                AiAgentToolCall.tool_call_id == "tool-ask-1",
            )
        )

    timeline_tool = next(item.tool for item in snapshot.timeline_items if item.tool and item.tool.tool_call_id == "tool-ask-1")
    assert tool_input == full_args
    assert timeline_tool.input_payload == full_args


async def test_platform_runtime_snapshot_should_keep_event_order_not_type_order(
    authenticated_client: AsyncClient,
) -> None:
    """运行态快照应按事件发生顺序回放，不能先消息后工具地按类型分组。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态顺序回放工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态顺序回放会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-order",
            message="先查工具再回答",
            image_attachment_ids=[],
        )
        run_model = run_start.run_model
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.started",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "list_workspace_components",
                    "tool_call_id": "tool-call-order",
                    "tool_args": {"workspace_id": workspace_id},
                },
            ),
        )
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.completed",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "list_workspace_components",
                    "tool_call_id": "tool-call-order",
                    "result": {"total": 0},
                },
            ),
        )
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="message.delta",
                run_id=run_model.run_id,
                session_id=session_id,
                content="工具后输出。",
            ),
        )
        await store.append_assistant_message(
            run_model,
            content="工具后输出。",
            reasoning_content=None,
            message_history=[{"kind": "summary"}],
        )
        await store.mark_terminal(run_model, status="completed", content="工具后输出。")

        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=AgentRuntimeContext(
                scope_type=scope.scope_type,
                workspace_id=workspace_id,
                source=scope.source,
            ),
        )

    assert [item.kind for item in snapshot.timeline_items] == ["message", "tool", "message"]
    assert snapshot.timeline_items[0].role == "user"
    assert snapshot.timeline_items[1].tool is not None
    assert snapshot.timeline_items[1].tool.output_payload == {"total": 0}
    assert snapshot.timeline_items[2].role == "assistant"
    assert snapshot.timeline_items[2].content == "工具后输出。"
    assert [item.order_index for item in snapshot.timeline_items] == [0, 1, 2]


async def test_platform_runtime_cancel_should_be_idempotent(
    authenticated_client: AsyncClient,
) -> None:
    """重复点击停止时，应复用同一个 cancelling 状态，不重复追加取消事件。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态停止幂等工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态停止幂等会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-cancel",
            message="开始长任务",
            image_attachment_ids=[],
        )

        first = await store.request_cancel(session_id=session_id, agent_id="component-manager")
        second = await store.request_cancel(session_id=session_id, agent_id="component-manager")

        assert first.run_id == run_start.run_model.run_id
        assert second.run_id == run_start.run_model.run_id
        result = await db_session.execute(
            select(AiAgentRunEvent.event)
            .where(AiAgentRunEvent.run_id == run_start.run_model.run_id)
            .order_by(AiAgentRunEvent.event_index.asc())
        )
        assert result.scalars().all() == ["run.started", "run.cancelling"]


async def test_platform_runtime_failed_run_should_close_running_tools(
    authenticated_client: AsyncClient,
) -> None:
    """run 失败时应把仍在运行的工具调用收敛为 error，避免快照残留进行中。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态失败工具收敛工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态失败工具收敛会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-tool-error-on-fail",
            message="创建页面",
            image_attachment_ids=[],
        )
        run_model = run_start.run_model
        await store.append_event(
            run_model,
            AgentRunEvent(
                event="tool.started",
                run_id=run_model.run_id,
                session_id=session_id,
                data={
                    "tool_name": "create_project_page",
                    "tool_call_id": "tool-create-page-1",
                    "tool_args": "",
                },
            ),
        )
        await store.mark_terminal(
            run_model,
            status="failed",
            error_code="AI_MODEL_STREAM_INTERRUPTED",
            error_message="模型连接中断，本次输出没有完整返回。",
        )
        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=AgentRuntimeContext(
                scope_type=scope.scope_type,
                workspace_id=workspace_id,
                source=scope.source,
            ),
        )
        tool_status = await db_session.scalar(
            select(AiAgentToolCall.status).where(
                AiAgentToolCall.run_id == run_model.run_id,
                AiAgentToolCall.tool_call_id == "tool-create-page-1",
            )
        )
        result = await db_session.execute(
            select(AiAgentRunEvent.event)
            .where(AiAgentRunEvent.run_id == run_model.run_id)
            .order_by(AiAgentRunEvent.event_index.asc())
        )

    timeline_tool = next(item.tool for item in snapshot.timeline_items if item.tool and item.tool.tool_call_id == "tool-create-page-1")
    assert tool_status == "error"
    assert timeline_tool.status == "error"
    assert timeline_tool.message == "模型连接中断，本次输出没有完整返回。"
    assert result.scalars().all() == ["run.started", "tool.started", "tool.error", "run.error"]


async def test_pydantic_runner_cancel_check_should_report_requested_cancel(
    authenticated_client: AsyncClient,
) -> None:
    """runner 取消检查发现外部请求时，应返回停止信号并允许调用方写取消终态。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "平台运行态取消收敛工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": "平台运行态取消收敛会话",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="platform-runtime-run-cancel-finalize",
            message="开始长任务",
            image_attachment_ids=[],
        )
        await store.request_cancel(session_id=session_id, agent_id="component-manager")

        should_stop, should_cancel = await PydanticAgentRunner(store)._cancel_event_if_requested(run_start.run_model)

        assert should_stop is True
        assert should_cancel is True
        await store.mark_terminal(run_start.run_model, status="cancelled", content="用户停止了当前运行。")
        latest_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert latest_run is not None
        assert latest_run.status == "cancelled"
        assert await store.get_active_run_model(session_id=session_id, agent_id="component-manager") is None
        result = await db_session.execute(
            select(AiAgentRunEvent.event)
            .where(AiAgentRunEvent.run_id == run_start.run_model.run_id)
            .order_by(AiAgentRunEvent.event_index.asc())
        )
        assert result.scalars().all() == ["run.started", "run.cancelling", "run.cancelled"]


async def test_agent_message_history_should_rebuild_from_run_deltas(
    authenticated_client: AsyncClient,
) -> None:
    """多轮历史应按 run delta 拼接，不能把前序历史重复写入后续 run。"""

    workspace_id, session_id, scope = await _create_history_workspace_session(authenticated_client, "delta 拼接")

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        first = await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-delta-run-1",
            user_text="第一轮问题",
            assistant_text="第一轮回答",
        )
        second = await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-delta-run-2",
            user_text="第二轮问题",
            assistant_text="第二轮回答",
        )

        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
        )
        first_run = await db_session.get(AiAgentRun, first.run_id)
        second_run = await db_session.get(AiAgentRun, second.run_id)

    assert workspace_id == scope.workspace_id
    assert [item["kind"] for item in rebuilt.message_json] == ["request", "response", "request", "response"]
    assert rebuilt.included_run_ids == ["history-delta-run-1", "history-delta-run-2"]
    assert first_run is not None and len(first_run.message_history_json) == 2
    assert second_run is not None and len(second_run.message_history_json) == 2
    assert second_run.message_history_json[0]["parts"][0]["content"] == "第二轮问题"


async def test_agent_message_history_should_exclude_current_continue_run(
    authenticated_client: AsyncClient,
) -> None:
    """HITL continue 重建前序历史时，应排除当前 paused run，避免 delta 重复提交。"""

    _, session_id, scope = await _create_history_workspace_session(authenticated_client, "continue 排除")

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-continue-run-1",
            user_text="前序问题",
            assistant_text="前序回答",
        )
        current = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="history-continue-run-2",
            message="需要确认的当前问题",
            image_attachment_ids=[],
        )
        await store.save_run_message_history(
            current.run_model,
            _history_delta(user_text="需要确认的当前问题", assistant_text="等待用户确认"),
        )
        current.run_model.status = "paused"
        await db_session.commit()

        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
            exclude_run_id=current.run_model.run_id,
        )
        rebuilt_without_exclusion = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
        )

    assert rebuilt.included_run_ids == ["history-continue-run-1"]
    assert rebuilt_without_exclusion.included_run_ids == ["history-continue-run-1", "history-continue-run-2"]


async def test_agent_message_history_should_preserve_large_payload_delta(
    authenticated_client: AsyncClient,
) -> None:
    """图片 URL、base64 与大工具结果应原样保留在本 run delta 中，且不写入后续 run。"""

    _, session_id, scope = await _create_history_workspace_session(authenticated_client, "大内容保留")
    image_url = "https://cdn.example.test/assets/rendered-image.png"
    image_base64 = "data:image/png;base64," + "A" * 2048
    large_tool_result = {"image_url": image_url, "base64": image_base64, "payload": "工具结果" + "B" * 4096}

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="history-large-payload-run-1",
            message="生成图片并返回大结果",
            image_attachment_ids=[],
        )
        await store.append_assistant_message(
            run_start.run_model,
            content="已生成图片。",
            message_history=_large_payload_delta(tool_result=large_tool_result),
        )
        await store.mark_terminal(run_start.run_model, status="completed", content="已生成图片。")
        second = await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-large-payload-run-2",
            user_text="继续下一轮",
            assistant_text="下一轮回答",
        )
        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
        )
        first_run = await db_session.get(AiAgentRun, run_start.run_model.run_id)
        second_run = await db_session.get(AiAgentRun, second.run_id)

    assert first_run is not None
    assert second_run is not None
    preserved_content = first_run.message_history_json[-1]["parts"][0]["content"]
    assert preserved_content == large_tool_result
    assert image_url in json.dumps(rebuilt.message_json, ensure_ascii=False)
    assert image_base64 in json.dumps(rebuilt.message_json, ensure_ascii=False)
    assert image_base64 not in json.dumps(second_run.message_history_json, ensure_ascii=False)


async def test_agent_message_history_checkpoint_should_skip_covered_deltas(
    authenticated_client: AsyncClient,
) -> None:
    """压缩检查点写入后，后续重建应跳过已覆盖 delta，但保留原始 run delta。"""

    _, session_id, scope = await _create_history_workspace_session(authenticated_client, "checkpoint 跳过")

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        first = await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-checkpoint-run-1",
            user_text="第一轮问题 " + "很长" * 300,
            assistant_text="第一轮回答 " + "很长" * 300,
        )
        second = await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-checkpoint-run-2",
            user_text="第二轮问题 " + "很长" * 300,
            assistant_text="第二轮回答 " + "很长" * 300,
        )
        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
        )
        budget = build_history_budget(
            SimpleNamespace(context_window_tokens=1200, max_output_tokens=100, compression_target_ratio=0.05),
            runtime_context=AgentRuntimeContext(scope_type=scope.scope_type, workspace_id=scope.workspace_id, source=scope.source),
        )
        processor = build_context_limit_processor(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
            budget=budget,
            rebuilt_history=rebuilt,
        )
        assert processor is not None
        compressed_messages = await processor(
            SimpleNamespace(),
            [*rebuilt.messages, ModelRequest(parts=[UserPromptPart(content="当前问题")])],
        )
        session_model = await db_session.get(AiAgentSession, session_id)
        assert session_model is not None
        checkpoint = session_model.summary_json

        rebuilt_after_checkpoint = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
        )
        third = await _finish_history_run(
            store,
            session_id=session_id,
            scope=scope,
            run_id="history-checkpoint-run-3",
            user_text="第三轮问题",
            assistant_text="第三轮回答",
        )
        rebuilt_after_new_delta = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="component-manager",
        )
        first_run = await db_session.get(AiAgentRun, first.run_id)
        second_run = await db_session.get(AiAgentRun, second.run_id)
        third_run = await db_session.get(AiAgentRun, third.run_id)

    assert len(compressed_messages) == 2
    assert isinstance(checkpoint, dict)
    assert checkpoint["covered_until_run_id"] == "history-checkpoint-run-2"
    assert rebuilt_after_checkpoint.included_run_ids == []
    assert rebuilt_after_checkpoint.message_json[0]["parts"][0]["part_kind"] == "system-prompt"
    assert rebuilt_after_new_delta.included_run_ids == ["history-checkpoint-run-3"]
    assert [item["kind"] for item in rebuilt_after_new_delta.message_json] == ["request", "request", "response"]
    assert first_run is not None and len(first_run.message_history_json) == 2
    assert second_run is not None and len(second_run.message_history_json) == 2
    assert third_run is not None and len(third_run.message_history_json) == 2


async def _read_next_sse_event(stream) -> AgentRunEvent:
    """读取异步 SSE 流中的下一条 AgentRunEvent。"""

    async for chunk in stream:
        text = chunk.decode("utf-8")
        for block in text.strip().split("\n\n"):
            if not block.startswith("data:"):
                continue
            raw_payload = block.removeprefix("data:").strip()
            return AgentRunEvent.model_validate_json(raw_payload)
    raise AssertionError("SSE stream ended before yielding an AgentRunEvent")


async def _create_history_workspace_session(
    authenticated_client: AsyncClient,
    suffix: str,
) -> tuple[int, str, AgentScopeContext]:
    """创建历史测试用工作空间和智能体会话。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": f"历史上下文工作空间 {suffix}", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "component-manager",
            "session_name": f"历史上下文会话 {suffix}",
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    return workspace_id, session_response.json()["session_id"], scope


async def _finish_history_run(
    store: PlatformAgentRuntimeStore,
    *,
    session_id: str,
    scope: AgentScopeContext,
    run_id: str,
    user_text: str,
    assistant_text: str,
) -> AiAgentRun:
    """创建并完成一个带 Pydantic AI delta 的测试 run。"""

    run_start = await store.start_run(
        session_id=session_id,
        agent_id="component-manager",
        scope=scope,
        run_id=run_id,
        message=user_text,
        image_attachment_ids=[],
    )
    await store.append_assistant_message(
        run_start.run_model,
        content=assistant_text,
        message_history=_history_delta(user_text=user_text, assistant_text=assistant_text),
    )
    await store.mark_terminal(run_start.run_model, status="completed", content=assistant_text)
    return run_start.run_model


def _history_delta(*, user_text: str, assistant_text: str) -> list[dict[str, object]]:
    """构造一轮 Pydantic AI 消息 delta。"""

    dumped = ModelMessagesTypeAdapter.dump_python(
        [
            ModelRequest(parts=[UserPromptPart(content=user_text)]),
            ModelResponse(parts=[TextPart(content=assistant_text)]),
        ],
        mode="json",
    )
    assert isinstance(dumped, list)
    return dumped


def _large_payload_delta(*, tool_result: dict[str, object]) -> list[dict[str, object]]:
    """构造包含大工具返回的 Pydantic AI 消息 delta。"""

    dumped = ModelMessagesTypeAdapter.dump_python(
        [
            ModelRequest(parts=[UserPromptPart(content="生成图片并返回大结果")]),
            ModelResponse(parts=[TextPart(content="准备调用渲染工具。")]),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="render_image",
                        tool_call_id="tool-large-payload",
                        content=tool_result,
                    )
                ]
            ),
        ],
        mode="json",
    )
    assert isinstance(dumped, list)
    return dumped
