"""文件功能：承载 AI streaming 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_ai_sessions_should_list_workspace_sessions_and_gate_new_runs(authenticated_client: AsyncClient) -> None:
    """会话列表按工作空间返回，只有创建新 run 时才校验路由必须落在 session scope 内。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 页面工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 页面一",
        content="<template><div>page-one</div></template>",
    )
    other_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 页面二",
        content="<template><div>page-two</div></template>",
    )

    create_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "页面一会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    session_id = created_payload["session_id"]
    assert created_payload["metadata"]["scope_type"] == "page"
    assert created_payload["metadata"]["workspace_name"] == "AI 页面工作空间"
    assert created_payload["metadata"]["project_name"] == "AI 页面项目"
    assert created_payload["metadata"]["page_title"] == "AI 页面一"

    list_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    other_list_response = await authenticated_client.get(
        "/api/ai/sessions",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": other_page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert other_list_response.status_code == 200
    other_list_payload = other_list_response.json()
    assert len(other_list_payload) == 1
    assert other_list_payload[0]["metadata"]["page_title"] == "AI 页面一"

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    assert messages_response.json() == []

    cross_route_messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": other_page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert cross_route_messages_response.status_code == 200
    assert cross_route_messages_response.json() == []

    out_of_scope_run_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": other_page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "这条消息不应启动新 run"},
    )
    assert out_of_scope_run_response.status_code == 409
    assert out_of_scope_run_response.json()["code"] == "AI_SESSION_ROUTE_OUT_OF_SCOPE"

async def test_ai_session_context_status_should_return_budget_and_summary(authenticated_client: AsyncClient) -> None:
    """上下文状态接口应返回模型预算、压缩目标和 Agno 会话摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 上下文工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 上下文项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 上下文页面",
        content="<template><div>context</div></template>",
    )
    config_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "上下文模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-context",
            "context_window_tokens": 4096,
            "max_output_tokens": 1024,
            "history_token_ratio": 0.4,
            "compression_target_ratio": 0.1,
            "advanced_config_json": {},
        },
    )
    assert config_response.status_code == 201
    bind_response = await authenticated_client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": config_response.json()["id"]},
    )
    assert bind_response.status_code == 200
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "上下文会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(
        app.state.ai_db.get_session,
        session_id,
        SessionType.TEAM,
        "1",
        True,
    )
    assert isinstance(session_model, TeamSession)
    session_model.summary = SessionSummary(summary="用户希望持续优化页面视觉。", topics=["页面优化"])
    session_model.upsert_run(
        TeamRunOutput(
            run_id="run-context-status",
            session_id=session_id,
            team_id=AGENT_COORDINATOR_AGENT_ID,
            messages=[
                Message(role="user", content="请优化页面" + "细节" * 200),
                Message(role="assistant", content="已记录优化方向" + "结果" * 200),
            ],
            status=RunStatus.completed,
        )
    )
    await asyncio.to_thread(app.state.ai_db.upsert_session, session_model)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/context-status",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_available"] is True
    assert payload["summary"] == "用户希望持续优化页面视觉。"
    assert payload["topics"] == ["页面优化"]
    assert payload["history_budget_tokens"] > payload["compression_target_tokens"]
    assert payload["compression_target_ratio"] == 0.1

async def test_ai_run_routes_should_stream_direct_page_apply(authenticated_client: AsyncClient, monkeypatch) -> None:
    """BFF 应直接透传页面改写工具的完成事件，而不是先进入确认暂停。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 流式工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 流式项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 流式页面",
        content="<template><div>draft</div></template>",
    )

    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "运行会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        return {
            "session_id": session_id,
            "metadata": scope.model_dump(mode="json"),
            "chat_history": [],
        }

    def fake_run_raw_sse(self, **kwargs: object):  # type: ignore[no-untyped-def]
        run_id = str(kwargs.get("run_id") or "run-1")

        async def generator():
            for event_index, payload in enumerate([
                {
                    "event": "ToolCallCompleted",
                    "run_id": run_id,
                    "session_id": session_id,
                    "event_index": 0,
                    "tool": {
                        "tool_call_id": "tool-1",
                        "tool_name": "apply_page_edits",
                        "result": {
                            "success": True,
                            "message": "页面代码已更新并生成新版本。",
                            "page_code": "PG1",
                            "version_no": 2,
                            "edits_applied": 1,
                        },
                    },
                },
                {
                    "event": "RunCompleted",
                    "run_id": run_id,
                    "session_id": session_id,
                    "event_index": 1,
                    "content": "已完成写回。",
                },
            ]):
                payload["event_index"] = event_index
                yield (
                    f"event: {payload['event']}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                ).encode("utf-8")

        return generator()

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.run_raw_sse", fake_run_raw_sse)

    stream_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "帮我优化一下页面"},
    )
    assert stream_response.status_code == 200
    assert "event: ToolCallCompleted" in stream_response.text
    assert "event: RunCompleted" in stream_response.text
    assert "event: RunPaused" not in stream_response.text
    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [item["event_index"] for item in event_payloads] == [0, 1]

async def test_ai_stream_should_mark_cancelled_and_close_upstream_when_client_interrupts() -> None:
    """客户端中断 SSE 消费时，应关闭 Agno 上游流、标记 run 取消并释放 session 锁。"""

    class BlockingAgnoStream:
        """模拟永不主动结束的 Agno async iterator，并记录 aclose 调用。"""

        def __init__(self) -> None:
            self.closed = False
            self.iterating = asyncio.Event()

        def __aiter__(self) -> "BlockingAgnoStream":
            return self

        async def __anext__(self) -> object:
            self.iterating.set()
            await asyncio.sleep(60)
            raise StopAsyncIteration

        async def aclose(self) -> None:
            self.closed = True

    class ActiveStream:
        """提供 _stream_agno_events 需要的 run_id 与 stream 字段。"""

        def __init__(self, stream: BlockingAgnoStream) -> None:
            self.stream = stream
            self.run_id = "run-abort-1"

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    scope = AgentScopeContext(scope_type="workspace", workspace_id=1, source="test")
    lock = asyncio.Lock()
    agno_stream = BlockingAgnoStream()
    marked_runs: list[tuple[str, RunStatus, str]] = []

    async def fake_ensure_session_access(**_: object) -> dict[str, object]:
        return {}

    def fake_get_session_run_lock(**_: object) -> asyncio.Lock:
        return lock

    async def fake_build_context_status_event(**kwargs: object) -> AgentRunEvent:
        return AgentRunEvent(
            event="context.status",
            run_id=str(kwargs.get("run_id") or ""),
            session_id=str(kwargs.get("session_id") or ""),
            data={},
        )

    def fake_normalize_event(**_: object) -> AgentRunEvent | None:
        return None

    async def fake_mark_run_terminal(
        *,
        run_id: str,
        status: RunStatus,
        content: str,
        **_: object,
    ) -> None:
        marked_runs.append((run_id, status, content))

    async def fake_stream_builder() -> ActiveStream:
        return ActiveStream(agno_stream)

    facade.ensure_session_access = fake_ensure_session_access  # type: ignore[method-assign]
    facade._get_session_run_lock = fake_get_session_run_lock  # type: ignore[method-assign]
    facade._build_context_status_event = fake_build_context_status_event  # type: ignore[method-assign]
    facade._normalize_event = fake_normalize_event  # type: ignore[method-assign]
    facade._mark_run_terminal = fake_mark_run_terminal  # type: ignore[method-assign]

    events = facade._stream_agno_events(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        session_id="session-abort-1",
        scope=scope,
        runtime_context=object(),  # type: ignore[arg-type]
        stream_builder=fake_stream_builder,
    )

    first_event = await events.__anext__()
    assert first_event.event == "context.status"
    assert lock.locked()

    next_event_task = asyncio.create_task(events.__anext__())
    await agno_stream.iterating.wait()
    next_event_task.cancel()
    try:
        await next_event_task
    except asyncio.CancelledError:
        pass
    else:  # pragma: no cover - 失败分支只用于让断言信息更清晰
        raise AssertionError("流式消费任务应被取消。")

    assert agno_stream.closed is True
    assert marked_runs == [
        ("run-abort-1", RunStatus.cancelled, "流式连接已断开，本次运行已停止。"),
    ]
    assert not lock.locked()

async def test_ai_session_messages_should_preserve_tool_metadata(authenticated_client: AsyncClient, monkeypatch) -> None:
    """会话消息读取应保留 Agno 持久化的工具调用参数与调用 ID，供前端回放详情。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具消息工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 工具消息项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 工具消息页面",
        content="<template><div>draft</div></template>",
    )

    tool_session = AgentSession(
        session_id="tool-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "工具消息会话"},
        metadata={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-tool-1",
                session_id="tool-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(
                        role="assistant",
                        content="我先读取资源列表。",
                        tool_calls=[
                            {
                                "id": "tool-assets-1",
                                "type": "function",
                                "function": {
                                    "name": "list_workspace_render_assets",
                                    "arguments": f'{{"workspace_id": {workspace_id}, "limit": 20}}',
                                },
                            }
                        ],
                    ),
                    Message(
                        role="tool",
                        content='{"total": 2, "items": ["hero.png", "cover.png"]}',
                        tool_name="list_workspace_render_assets",
                        tool_call_id="tool-assets-1",
                        tool_args={"workspace_id": workspace_id, "limit": 20},
                    ),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "tool-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        return tool_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id="tool-session-1",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            compression_enabled=True,
            compression_required=False,
            summary_available=False,
            summary=None,
            topics=[],
            summary_updated_at=None,
            context_window_tokens=4096,
            max_output_tokens=1024,
            history_token_ratio=0.4,
            compression_target_ratio=0.1,
            safety_margin_tokens=256,
            current_input_tokens=0,
            fixed_context_tokens=0,
            history_budget_tokens=2048,
            compression_target_tokens=512,
            estimated_history_tokens=0,
            retained_recent_history_tokens=0,
            retained_recent_message_count=2,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        "/api/ai/sessions/tool-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assistant_message = messages[0]
    tool_message = messages[1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["tool_calls"] == [
        {
            "id": "tool-assets-1",
            "type": "function",
            "function": {
                "name": "list_workspace_render_assets",
                "arguments": f'{{"workspace_id": {workspace_id}, "limit": 20}}',
            },
        }
    ]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_name"] == "list_workspace_render_assets"
    assert tool_message["tool_call_id"] == "tool-assets-1"
    assert tool_message["tool_args"] == {"workspace_id": workspace_id, "limit": 20}
    assert tool_message["tool_call_error"] is None
    assert tool_message["tool_calls"] == []

    runtime_response = await authenticated_client.get(
        "/api/ai/sessions/tool-session-1/runtime",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert runtime_response.status_code == 200
    runtime_payload = runtime_response.json()
    assert "messages" not in runtime_payload
    assert "tool_details" not in runtime_payload
    timeline_items = runtime_payload["timeline_items"]
    assert [(item["kind"], item["role"]) for item in timeline_items] == [("message", "assistant"), ("tool", None), ("run_status", None)]
    assert timeline_items[1]["tool"]["tool_call_id"] == "tool-assets-1"
    assert timeline_items[1]["tool"]["tool_name"] == "list_workspace_render_assets"

async def test_ai_session_messages_should_hide_system_and_split_reasoning(authenticated_client: AsyncClient, monkeypatch) -> None:
    """会话历史不返回 system 消息，并把 thinking 内容拆成独立字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 思考消息工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 思考消息项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 思考消息页面",
        content="<template><div>draft</div></template>",
    )

    reasoning_session = AgentSession(
        session_id="reasoning-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "思考消息会话"},
        metadata={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-reasoning-1",
                session_id="reasoning-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="system", content="内部系统提示"),
                    Message(role="user", content="你好"),
                    Message(role="assistant", content="<think>先判断用户意图</think>\n你好！", reasoning_content="模型原生思考"),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "reasoning-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        return reasoning_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/reasoning-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "\n你好！"
    assert messages[1]["reasoning_content"] == "模型原生思考\n\n先判断用户意图"

async def test_ai_session_messages_should_hide_agno_context_note(authenticated_client: AsyncClient, monkeypatch) -> None:
    """Agno 为图片上下文注入的 Take note 消息不应渲染成用户消息。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 框架消息过滤工作空间")
    context_note_session = AgentSession(
        session_id="context-note-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "框架消息过滤会话"},
        metadata={
            "scope_type": "workspace",
            "workspace_id": workspace_id,
            "source": "editor-agent-sidebar",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-context-note-1",
                session_id="context-note-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="真实用户输入"),
                    Message(
                        role="user",
                        content="Take note of the following content",
                        images=[Image(content=b"fake-image", mime_type="image/png")],
                    ),
                    Message(role="assistant", content="真实助手回复"),
                    Message(role="assistant", content="历史注入回复", from_history=True),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "context-note-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return context_note_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/context-note-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["content"] for item in messages] == ["真实用户输入", "真实助手回复"]
    assert [item["role"] for item in messages] == ["user", "assistant"]

async def test_ai_cancelled_raw_run_should_preserve_input_and_streamed_content(authenticated_client: AsyncClient) -> None:
    """raw SSE 取消后若 Agno 未写 messages，应补偿真实输入和已展示内容。"""

    workspace_id = await _create_workspace(authenticated_client, "AI raw 取消补偿工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI raw 取消补偿项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI raw 取消补偿页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "raw 取消补偿会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-raw-cancel-preserve"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=TeamRunOutput(
            run_id=run_id,
            session_id=session_id,
            team_id=AGENT_COORDINATOR_AGENT_ID,
            user_id="1",
            input=TeamRunInput(input_content="真实取消输入"),
            status=RunStatus.cancelled,
            content=f"Run {run_id} was cancelled",
        ),
    )

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    async with get_session_factory()() as db_session:
        facade = AgentSessionFacade(app=app, current=_build_auth_context(), session=db_session)
        await facade._preserve_cancelled_raw_run_messages(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            run_id=run_id,
            fallback_user_message="兜底输入不应优先",
            assistant_content="已流出的正文。",
            reasoning_content="已展示 reasoning。",
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "真实取消输入"
    assert messages[1]["content"] == "已流出的正文。"
    assert messages[1]["reasoning_content"] == "已展示 reasoning。"

    session_detail = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    assert isinstance(session_detail, TeamSession)
    run = session_detail.get_run(run_id)
    assert run is not None
    assert run.metadata is not None
    assert run.metadata["user_cancel_preserved"] is True

async def test_ai_cancelled_session_messages_should_lazy_preserve_input_and_run_content(
    authenticated_client: AsyncClient,
) -> None:
    """读取消息时应懒补偿 cancelled run 中已持久化但未写入 messages 的内容。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 懒补偿工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "懒补偿会话",
            "scope": {
                "workspace_id": workspace_id,
                "scope_type": "workspace",
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-lazy-cancel-preserve"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id="1",
            input=RunInput(input_content="创建一个复杂组件"),
            status=RunStatus.cancelled,
            content="已经完成设计和代码校验，准备创建组件。",
            reasoning_content="先分析需求，再准备调用创建工具。",
            messages=[],
        ),
    )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "创建一个复杂组件"
    assert messages[1]["content"] == "已经完成设计和代码校验，准备创建组件。"
    assert messages[1]["reasoning_content"] == "先分析需求，再准备调用创建工具。"

async def test_ai_raw_sse_cancelled_event_should_trigger_preservation() -> None:
    """raw SSE 收到 Agno 取消终态时，应把跟踪到的用户输入和 delta 交给补偿流程。"""

    class FakeRawEvent:
        """提供 Agno SSE formatter 所需的 event 与 to_dict。"""

        def __init__(self, **payload: object) -> None:
            self.event = str(payload.get("event"))
            self._payload = payload
            for key, value in payload.items():
                setattr(self, key, value)

        def to_dict(self) -> dict[str, object]:
            return dict(self._payload)

    async def fake_raw_stream():
        yield FakeRawEvent(event="TeamRunStarted", run_id="run-raw-event", session_id="session-raw-event")
        yield FakeRawEvent(
            event="TeamRunContent",
            run_id="run-raw-event",
            session_id="session-raw-event",
            content="已输出正文",
        )
        yield FakeRawEvent(
            event="ReasoningContentDelta",
            run_id="run-raw-event",
            session_id="session-raw-event",
            reasoning_content="已输出思考",
        )
        yield FakeRawEvent(event="TeamRunCancelled", run_id="run-raw-event", session_id="session-raw-event")

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=fake_raw_stream(), run_id="run-raw-event")

    preserved_payloads: list[dict[str, object]] = []
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(SimpleNamespace(metadata={}))

    async def fake_preserve(**kwargs: object) -> None:
        preserved_payloads.append(dict(kwargs))

    facade._preserve_cancelled_raw_run_messages = fake_preserve

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id="session-raw-event",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message="真实用户输入",
            stream_builder=fake_stream_builder,
        )
    ]

    assert len(chunks) == 4
    assert preserved_payloads == [
        {
            "session_id": "session-raw-event",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "run_id": "run-raw-event",
            "fallback_user_message": "真实用户输入",
            "assistant_content": "已输出正文",
            "reasoning_content": "已输出思考",
        }
    ]

async def test_ai_raw_sse_string_stream_should_trigger_cancelled_preservation() -> None:
    """raw SSE 若已被 Agno 格式化为字符串，流结束后仍应尝试按 DB 状态补偿取消消息。"""

    async def fake_raw_stream():
        yield "event: TeamRunStarted\ndata: {\"run_id\":\"run-raw-string\"}\n\n"
        yield "event: TeamRunCancelled\ndata: {\"run_id\":\"run-raw-string\"}\n\n"

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=fake_raw_stream(), run_id="run-raw-string")

    preserved_payloads: list[dict[str, object]] = []
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(SimpleNamespace(metadata={}))

    async def fake_preserve(**kwargs: object) -> None:
        preserved_payloads.append(dict(kwargs))

    facade._preserve_cancelled_raw_run_messages = fake_preserve

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id="session-raw-string",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message="字符串流用户输入",
            stream_builder=fake_stream_builder,
        )
    ]

    assert len(chunks) == 2
    assert preserved_payloads == [
        {
            "session_id": "session-raw-string",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "run_id": "run-raw-string",
            "fallback_user_message": "字符串流用户输入",
            "assistant_content": None,
            "reasoning_content": None,
        }
    ]

async def test_ai_raw_sse_object_events_should_continue_existing_event_index() -> None:
    """非 background 原始事件包装时，应沿用已有 run.events 游标继续编号。"""

    class FakeRawEvent:
        """提供 Agno SSE formatter 所需的 event 与 to_dict。"""

        def __init__(self, **payload: object) -> None:
            self.event = str(payload.get("event"))
            self._payload = payload
            for key, value in payload.items():
                setattr(self, key, value)

        def to_dict(self) -> dict[str, object]:
            return dict(self._payload)

    run_id = "run-continue-index"
    session_id = "session-continue-index"
    session_detail = TeamSession(
        session_id=session_id,
        team_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        team_data={"team_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            TeamRunOutput(
                run_id=run_id,
                session_id=session_id,
                team_id=AGENT_COORDINATOR_AGENT_ID,
                events=[
                    {"event": "TeamRunStarted", "run_id": run_id},
                    {"event": "TeamRunPaused", "run_id": run_id},
                ],
                status=RunStatus.running,
            )
        ],
    )

    async def fake_raw_stream():
        yield FakeRawEvent(event="TeamRunContent", run_id=run_id, session_id=session_id, content="继续输出")
        yield FakeRawEvent(event="TeamRunCompleted", run_id=run_id, session_id=session_id, content="完成")

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=fake_raw_stream(), run_id=run_id)

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(session_detail)

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message=None,
            stream_builder=fake_stream_builder,
        )
    ]

    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for chunk in chunks
        for line in chunk.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert [payload["event_index"] for payload in event_payloads] == [2, 3]

async def test_ai_coordinator_session_messages_should_be_visible(authenticated_client: AsyncClient, monkeypatch) -> None:
    """统一智能体使用 AgentSession 持久化时，历史消息应能被会话接口读取。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 总控消息工作空间")
    agent_session = AgentSession(
        session_id="agent-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "智能体会话"},
        metadata={
            "scope_type": "workspace",
            "workspace_id": workspace_id,
            "project_id": None,
            "page_id": None,
            "component_id": None,
            "source": "editor-agent-sidebar",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="agent-run-1",
                session_id="agent-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="你好"),
                    Message(role="assistant", content="你好！很高兴为你服务。"),
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "agent-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return agent_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/agent-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-agent-sidebar",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    messages = response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert [item["content"] for item in messages] == ["你好", "你好！很高兴为你服务。"]

async def test_ai_agent_run_events_should_be_normalized_for_editor() -> None:
    """Agno Agent 事件应转换成前端已支持的统一 SSE 事件名。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-agent-sidebar",
    )

    content_event = facade._normalize_event(
        raw_event=RunContentEvent(run_id="agent-run-1", session_id="agent-session-1", content="<think>组织回复</think>你好"),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    completed_event = facade._normalize_event(
        raw_event=RunCompletedEvent(run_id="agent-run-1", session_id="agent-session-1", content="完成"),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    content_completed_event = facade._normalize_event(
        raw_event={
            "event": "RunContentCompleted",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": "一段内容已完成",
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    output_event = facade._normalize_event(
        raw_event=RunOutput(run_id="agent-run-1", session_id="agent-session-1", agent_id=AGENT_COORDINATOR_AGENT_ID, content="完成"),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    tool_event = facade._normalize_event(
        raw_event={
            "event": "ToolCallCompleted",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": "apply_component_edits(component_id=6, edits=..., change_note=...) completed in 0.0111s.",
            "tool": {
                "tool_name": "apply_component_edits",
                "tool_call_id": "tool-call-1",
                "result": {
                    "success": True,
                    "component_id": 6,
                    "preview": {"changed_files": ["Component.vue"]},
                },
            },
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )

    assert content_event is not None
    assert content_event.event == "message.delta"
    assert content_event.content == "你好"
    assert content_event.data["reasoning_content"] == "组织回复"
    assert completed_event is not None
    assert completed_event.event == "run.completed"
    assert completed_event.content == "完成"
    assert content_completed_event is None
    assert output_event is not None
    assert output_event.event == "run.completed"
    assert output_event.content == "完成"
    assert tool_event is not None
    assert tool_event.event == "tool.completed"
    assert tool_event.data["result"] == {
        "success": True,
        "component_id": 6,
        "preview": {"changed_files": ["Component.vue"]},
    }
    assert tool_event.data["message"].endswith("completed in 0.0111s.")

async def test_ai_stream_delta_should_preserve_markdown_boundaries() -> None:
    """流式 delta 不应被 trim 掉开头换行，否则列表会在输出过程中粘到上一段。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-agent-sidebar",
    )

    content_event = facade._normalize_event(
        raw_event=RunContentEvent(
            run_id="agent-run-1",
            session_id="agent-session-1",
            content="\n\n- **页面标题**：234234",
        ),
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )

    assert content_event is not None
    assert content_event.event == "message.delta"
    assert content_event.content == "\n\n- **页面标题**：234234"

async def test_ai_reasoning_stream_delta_should_preserve_newline_boundaries() -> None:
    """reasoning 流式片段应保留换行边界，避免思考过程完成后才重新排版。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-agent-sidebar",
    )

    reasoning_event = facade._normalize_event(
        raw_event={
            "event": "RunContent",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": None,
            "reasoning_content": "\n\n- **检查页面**：确认当前路由",
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )
    newline_event = facade._normalize_event(
        raw_event={
            "event": "RunContent",
            "run_id": "agent-run-1",
            "session_id": "agent-session-1",
            "content": None,
            "reasoning_content": "\n",
        },
        runtime_context=runtime_context,
        session_id="agent-session-1",
    )

    assert reasoning_event is not None
    assert reasoning_event.event == "message.delta"
    assert reasoning_event.data["reasoning_content"] == "\n\n- **检查页面**：确认当前路由"
    assert newline_event is not None
    assert newline_event.event == "message.delta"
    assert newline_event.data["reasoning_content"] == "\n"

async def test_extract_tool_error_info_should_keep_structured_code() -> None:
    """ToolCallError 若携带结构化错误对象，应保留 message 与 code。"""

    message, code, repair_attempted, repair_succeeded, repair_reason = _extract_tool_error_info(
        payload={
            "error": {
                "code": "AI_PAGE_DIFF_CONFLICT",
                "detail": "Unified Diff 无法应用：上下文内容不匹配。",
            }
        },
        tool_execution={
            "tool_name": "apply_page_edits",
            "tool_call_id": "tool-error-1",
        },
    )

    assert code == "AI_PAGE_DIFF_CONFLICT"
    assert message == "Unified Diff 无法应用：上下文内容不匹配。"
    assert repair_attempted is False
    assert repair_succeeded is False
    assert repair_reason is None
