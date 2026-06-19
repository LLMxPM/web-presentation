"""文件功能：承载 AI extra 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_ai_runtime_timeline_should_not_render_structured_completed_payload_as_assistant(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """RunCompleted 的结构化聚合内容不应在刷新后显示成 assistant 正文。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 聚合完成事件工作空间")
    run_id = "run-structured-completed-payload"
    session_id = "session-structured-completed-payload"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "聚合完成事件会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[Message(role="user", content="返回结构化结果")],
                events=[
                    {
                        "event": "RunCompleted",
                        "run_id": run_id,
                        "content": '{"messages": [{"role": "assistant", "content": "完成"}], "tools": []}',
                    }
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-structured-completed-payload"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return _build_empty_context_status(session_id, retained_recent_message_count=1)

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    assert [
        (item["kind"], item["role"], item["content"])
        for item in response.json()["timeline_items"]
    ] == [
        ("message", "user", "返回结构化结果"),
        ("run_status", None, "运行已完成。"),
    ]

async def test_ai_error_should_not_preserve_streamed_delta_in_agno_history(authenticated_client: AsyncClient) -> None:
    """普通执行报错时，已流出的半截内容不应补写进 Agno 历史。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 报错丢弃工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 报错丢弃项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 报错丢弃页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "报错丢弃会话",
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
    run_id = "run-error-no-preserve"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
            messages=[Message(role="user", content="请生成一段长内容")],
        ),
    )
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="请生成一段长内容",
        )
        await service.append_event(run_id=run_id, event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id))
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="这段不应保留"),
        )
        await service.mark_terminal(task=task, status="failed", error_message="模型调用失败。")

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
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["user"]

async def test_ai_run_event_append_should_retry_sequence_conflict(
    authenticated_client: AsyncClient,
) -> None:
    """Redis Stream 追加事件时应生成严格递增的 sequence。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 事件重试工作空间")
    run_id = "run-event-retry"
    scope = AgentScopeContext(scope_type="workspace", workspace_id=workspace_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id="session-event-retry",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="事件重试",
        )
        event = await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.cancelling", run_id=run_id, session_id="session-event-retry"),
        )
        events = await service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)

    assert event is not None
    assert event.sequence == 1
    assert [item.sequence for item in events] == [1]

async def test_ai_mark_paused_should_not_duplicate_event_with_stale_task(
    authenticated_client: AsyncClient,
) -> None:
    """恢复 UI 使用旧 task 补偿暂停态时，不应重复写入同一 pause 事件序号。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 暂停竞态工作空间")
    run_id = "run-stale-mark-paused"
    session_id = "session-stale-mark-paused"
    scope = AgentScopeContext(scope_type="workspace", workspace_id=workspace_id)
    requirement = AgentPendingRequirement(
        kind="confirmation",
        run_id=run_id,
        session_id=session_id,
        tool_name="apply_project_route_tree",
        tool_execution={
            "tool_call_id": "tool-stale-pause",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        },
    )

    async with get_session_factory()() as stale_session:
        stale_service = AiAgentRunService(stale_session)
        stale_task = await stale_service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="暂停竞态",
        )
        await stale_service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id),
        )

        async with get_session_factory()() as fresh_session:
            fresh_service = AiAgentRunService(fresh_session)
            fresh_task = await fresh_service.get_task_by_run(run_id=run_id, user_id=1)
            assert fresh_task is not None
            await fresh_service.mark_paused(task=fresh_task, pending_requirement=requirement)

        restored_task = await stale_service.mark_paused(task=stale_task, pending_requirement=requirement)
        events = await stale_service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)

    assert restored_task.status == "paused"
    assert restored_task.event_sequence == 2
    assert [event.event for event in events] == ["run.started", "run.paused"]
    assert [event.sequence for event in events] == [1, 2]

async def test_ai_mark_paused_should_not_reopen_terminal_run(
    authenticated_client: AsyncClient,
) -> None:
    """已完成 run 不应被 Agno 陈旧 requirement 重新覆盖成 paused。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 终态保护工作空间")
    run_id = "run-terminal-mark-paused"
    session_id = "session-terminal-mark-paused"
    scope = AgentScopeContext(scope_type="workspace", workspace_id=workspace_id)
    requirement = AgentPendingRequirement(
        kind="confirmation",
        run_id=run_id,
        session_id=session_id,
        tool_name="apply_project_route_tree",
        tool_execution={
            "tool_call_id": "tool-terminal-pause",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        },
    )

    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="终态保护",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.completed", run_id=run_id, session_id=session_id),
        )
        restored_task = await service.mark_paused(task=task, pending_requirement=requirement)
        events = await service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)

    assert restored_task.status == "completed"
    assert restored_task.pending_requirement_json is None
    assert [event.event for event in events] == ["run.completed"]

async def test_ai_session_active_run_should_not_restore_requirement_from_completed_task(
    authenticated_client: AsyncClient,
) -> None:
    """completed task 应修正 Agno 终态残留，而不是恢复旧 requirement。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Feedback Restore 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Feedback Restore 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-completed-feedback"
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-restore",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "这次优先调整哪个区域？",
                    "header": "范围",
                    "options": [{"label": "首屏"}, {"label": "全页面"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.completed,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="触发结构化提问",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.completed", run_id=run_id, session_id=session_id, data={}),
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload is None

    async with get_session_factory()() as db_session:
        task = await AiAgentRunService(db_session).get_task_by_run(run_id=run_id, user_id=1)
    assert task is not None
    assert task.status == "completed"
    assert task.pending_requirement_json is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    run = session_model.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    assert not run.requirements
    assert run.tools
    assert run.tools[0].requires_user_input is False
    assert run.tools[0].answered is True

async def test_ai_completed_confirmed_route_tool_should_cleanup_agno_hitl(
    authenticated_client: AsyncClient,
) -> None:
    """确认执行后的项目路由工具完成时，Agno session 不应残留旧确认弹窗。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Route HITL Cleanup 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Route HITL Cleanup 项目")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Route HITL Cleanup 会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "editor-agent-sidebar",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-completed-route-confirm"
    route_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-route-confirm-cleanup",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.completed,
            tools=[route_tool],
            requirements=[RunRequirement(tool_execution=route_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="project",
        workspace_id=workspace_id,
        project_id=project_id,
        source="editor-agent-sidebar",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="确认路由树写入",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="run.completed",
                run_id=run_id,
                session_id=session_id,
                data={},
            ),
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "scope_type": "project",
            "source": "editor-agent-sidebar",
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    assert isinstance(session_model, TeamSession)
    run = session_model.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    assert not run.requirements
    assert run.tools
    assert run.tools[0].requires_confirmation is False
    assert run.tools[0].confirmed is True

async def test_ai_session_active_run_should_restore_feedback_requirement_from_failed_task(
    authenticated_client: AsyncClient,
) -> None:
    """continue 失败后若 Agno 仍有未解决 ask_user，active-run 应恢复为 paused。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Feedback Failed Restore 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Feedback Failed Restore 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-failed-feedback"
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-failed-restore",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "组件 default slot 的默认内容应如何处理？",
                    "header": "Slot 默认内容",
                    "options": [{"label": "完全清空"}, {"label": "保留占位"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.error,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="继续结构化提问失败",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="run.error",
                run_id=run_id,
                session_id=session_id,
                data={"message": "当前会话没有待继续的暂停运行。", "code": "AI_RUN_NOT_PAUSED"},
            ),
        )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "paused"
    assert payload["pending_requirement"]["kind"] == "user_feedback"
    assert payload["pending_requirement"]["tool_name"] == "ask_user"
    async with get_session_factory()() as db_session:
        task = await AiAgentRunService(db_session).get_task_by_run(run_id=run_id, user_id=1)
    assert task is not None
    assert task.status == "paused"
    assert task.pending_requirement_json is not None

async def test_ai_startup_recovery_should_keep_interrupted_feedback_run_paused(
    authenticated_client: AsyncClient,
) -> None:
    """服务重启恢复时，已进入 ask_user 的 running task 不应被取消。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Startup Feedback Restore 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Startup Feedback Restore 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-startup-feedback"
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-startup",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "预览 presets 中如何体现 slot 内容？",
                    "header": "Presets 策略",
                    "options": [{"label": "仅文字描述"}, {"label": "描述加源码"}],
                    "multi_select": False,
                }
            ],
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )
    scope = AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source="editor-component-library",
    )
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="重启前进入结构化提问",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id, data={}),
        )

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    async with get_session_factory()() as db_session:
        recovered_count = await AiAgentRunService(db_session).recover_interrupted_tasks(ai_db=app.state.ai_db)
        task = await AiAgentRunService(db_session).get_task_by_run(run_id=run_id, user_id=1)
        events = await AiAgentRunService(db_session).list_events_after(
            run_id=run_id,
            user_id=1,
            after_sequence=0,
        )

    assert recovered_count >= 1
    assert task is not None
    assert task.status == "paused"
    assert task.pending_requirement_json is not None
    assert task.pending_requirement_json["kind"] == "user_feedback"
    assert [event.event for event in events] == ["run.started", "run.paused"]
