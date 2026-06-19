"""文件功能：验证 Pydantic AI 切换后的平台自有智能体运行态闭环。"""

from __future__ import annotations

from httpx import AsyncClient

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.db.session import get_session_factory
from app.schemas.agent import AgentRunEvent, AgentScopeContext


async def test_platform_runtime_should_persist_events_messages_and_snapshot(authenticated_client: AsyncClient) -> None:
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
