"""文件功能：验证 Pydantic AI 切换后的平台自有智能体运行态闭环。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.pydantic_runner import PydanticAgentRunner
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentRunEvent, AiAgentToolCall
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


async def test_pydantic_runner_should_finalize_requested_cancel(
    authenticated_client: AsyncClient,
) -> None:
    """runner 发现外部取消请求时，应追加 run.cancelled 并释放 active run。"""

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

        should_stop, cancel_sse = await PydanticAgentRunner(store)._cancel_event_if_requested(run_start.run_model)

        assert should_stop is True
        assert cancel_sse is not None
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
