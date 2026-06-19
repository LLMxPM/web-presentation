"""文件功能：承载 AI streaming 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_extract_tool_error_info_should_parse_repair_metadata_from_json_string() -> None:
    """ToolCallError 若只携带 JSON 字符串错误体，也应解包 repair 结构化字段。"""

    message, code, repair_attempted, repair_succeeded, repair_reason = _extract_tool_error_info(
        payload={
            "error": json.dumps(
                {
                    "message": "Unified Diff 无法应用：上下文内容不匹配。 自动重定位失败：hunk #1 未找到窗口。",
                    "code": "AI_PAGE_DIFF_CONFLICT",
                    "repair_attempted": True,
                    "repair_succeeded": False,
                    "repair_reason": "hunk #1 未找到窗口。",
                },
                ensure_ascii=False,
            )
        },
        tool_execution={
            "tool_name": "apply_page_edits",
            "tool_call_id": "tool-error-2",
        },
    )

    assert code == "AI_PAGE_DIFF_CONFLICT"
    assert message == "Unified Diff 无法应用：上下文内容不匹配。 自动重定位失败：hunk #1 未找到窗口。"
    assert repair_attempted is True
    assert repair_succeeded is False
    assert repair_reason == "hunk #1 未找到窗口。"

async def test_ai_active_run_cancel_route_should_proxy_interrupt_request(authenticated_client: AsyncClient, monkeypatch) -> None:
    """BFF 应暴露 session 级 run 中断接口，并代理给当前 active run。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 中断工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 中断项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 中断页面",
        content="<template><div>draft</div></template>",
    )

    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "中断会话",
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

    async def fake_cancel_active_run(  # type: ignore[no-untyped-def]
        self,
        *,
        session_id: str,
        agent_id: str,
        scope,
        force: bool = False,
        tool_call_id: str | None = None,
    ):
        assert session_id
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        assert force is False
        assert tool_call_id is None
        return {
            "run_id": "run-interrupt-1",
            "session_id": session_id,
            "cancel_requested": True,
        }

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.cancel_active_run", fake_cancel_active_run)

    cancel_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={
            "session_id": session_id,
        },
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json() == {
        "run_id": "run-interrupt-1",
        "session_id": session_id,
        "cancel_requested": True,
    }

async def test_ai_cancelled_runtime_snapshot_should_restore_tool_timeline(authenticated_client: AsyncClient, monkeypatch) -> None:
    """停止前的工具事件应从 runtime snapshot 恢复，且不伪造成 Agno tool 消息。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 停止工具恢复工作空间")
    session_id = "cancelled-tool-timeline-session"
    run_id = "run-preserve-tool-details"
    cancelled_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "停止工具恢复会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[],
                events=[
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "tool_args": {"workspace_id": workspace_id}},
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "result": {"total": 2}},
                    },
                ],
                status=RunStatus.cancelled,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "cancelled-tool-timeline-session"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return cancelled_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
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
            retained_recent_message_count=0,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    runtime_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={
            "workspace_id": workspace_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert runtime_response.status_code == 200, runtime_response.text
    runtime_payload = runtime_response.json()
    assert "messages" not in runtime_payload
    assert "tool_details" not in runtime_payload
    timeline_items = runtime_payload["timeline_items"]
    tool_items = [item for item in timeline_items if item["kind"] == "tool"]
    assert len(tool_items) == 1
    tool_item = tool_items[0]
    assert tool_item["run_id"] == run_id
    assert tool_item["tool"]["tool_name"] == "list_workspace_render_assets"
    assert tool_item["tool"]["status"] == "completed"
    assert tool_item["tool"]["input_payload"] == {"workspace_id": workspace_id}
    assert tool_item["tool"]["output_payload"] == {"total": 2}

async def test_ai_runtime_snapshot_should_attach_delegate_member_runs(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """delegate_task_to_member 触发的成员 run 应独立进入 member_runs，并从父时间线隐藏子工具。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 成员运行快照工作空间")
    session_id = "delegate-member-run-session"
    parent_run_id = "parent-run-delegate-member"
    member_run_id = "member-run-resource-manager"
    timeline_session = TeamSession(
        session_id=session_id,
        team_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "成员运行快照会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        team_data={"team_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            TeamRunOutput(
                run_id=parent_run_id,
                session_id=session_id,
                team_id=AGENT_COORDINATOR_AGENT_ID,
                team_name="内容助手",
                created_at=10,
                messages=[Message(role="user", content="整理资源")],
                events=[
                    {
                        "event": "TeamToolCallStarted",
                        "run_id": parent_run_id,
                        "tool": {
                            "tool_call_id": "delegate-call-resource",
                            "tool_name": "delegate_task_to_member",
                            "tool_args": {"member_id": RESOURCE_MANAGER_AGENT_ID, "task": "整理资源"},
                        },
                    },
                    {
                        "event": "TeamToolCallCompleted",
                        "run_id": parent_run_id,
                        "tool": {
                            "tool_call_id": "delegate-call-resource",
                            "tool_name": "delegate_task_to_member",
                            "result": {"success": True},
                        },
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": member_run_id,
                        "parent_run_id": parent_run_id,
                        "agent_id": RESOURCE_MANAGER_AGENT_ID,
                        "agent_name": "资源助手",
                        "tool": {
                            "tool_call_id": "child-tool-list-assets",
                            "tool_name": "list_workspace_render_assets",
                            "tool_args": {"workspace_id": workspace_id},
                            "result": {"total": 2},
                        },
                    },
                ],
                member_responses=[
                    RunOutput(
                        run_id=member_run_id,
                        parent_run_id=parent_run_id,
                        session_id=session_id,
                        agent_id=RESOURCE_MANAGER_AGENT_ID,
                        agent_name="资源助手",
                        created_at=11,
                        messages=[Message(role="assistant", content="已整理资源。")],
                        events=[
                            {
                                "event": "ToolCallStarted",
                                "run_id": member_run_id,
                                "parent_run_id": parent_run_id,
                                "agent_id": RESOURCE_MANAGER_AGENT_ID,
                                "agent_name": "资源助手",
                                "tool": {
                                    "tool_call_id": "child-tool-list-assets",
                                    "tool_name": "list_workspace_render_assets",
                                    "tool_args": {"workspace_id": workspace_id},
                                },
                            },
                            {
                                "event": "ToolCallCompleted",
                                "run_id": member_run_id,
                                "parent_run_id": parent_run_id,
                                "agent_id": RESOURCE_MANAGER_AGENT_ID,
                                "agent_name": "资源助手",
                                "tool": {
                                    "tool_call_id": "child-tool-list-assets",
                                    "tool_name": "list_workspace_render_assets",
                                    "result": {"total": 2},
                                },
                            },
                        ],
                        status=RunStatus.completed,
                    )
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "delegate-member-run-session"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
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
            retained_recent_message_count=1,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    parent_tools = [item["tool"]["tool_name"] for item in payload["timeline_items"] if item["kind"] == "tool"]
    assert parent_tools == ["delegate_task_to_member"]

    member_runs = payload["member_runs"]
    assert len(member_runs) == 1
    member_run = member_runs[0]
    assert member_run["parent_run_id"] == parent_run_id
    assert member_run["run_id"] == member_run_id
    assert member_run["agent_id"] == RESOURCE_MANAGER_AGENT_ID
    assert member_run["agent_name"] == "资源助手"
    assert member_run["delegate_tool_call_id"] == "delegate-call-resource"
    child_tool_items = [item for item in member_run["timeline_items"] if item["kind"] == "tool"]
    assert len(child_tool_items) == 1
    assert child_tool_items[0]["tool"]["tool_name"] == "list_workspace_render_assets"
    assert child_tool_items[0]["tool"]["input_payload"] == {"workspace_id": workspace_id}
    assert child_tool_items[0]["tool"]["output_payload"] == {"total": 2}

async def test_ai_timeline_should_keep_separate_missing_call_id_pairs(authenticated_client: AsyncClient, monkeypatch) -> None:
    """缺少 tool_call_id 的连续同名工具调用应按 started/completed 配对，不应互相覆盖。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具配对工作空间")
    run_id = "run-tool-pairs-without-call-id"
    session_id = "session-tool-pairs-without-call-id"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "工具配对会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[Message(role="user", content="连续读取资源")],
                events=[
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "tool_args": {"page": 1}},
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "result": {"total": 1}},
                    },
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "tool_args": {"page": 2}},
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {"tool_name": "list_workspace_render_assets", "result": {"total": 2}},
                    },
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-tool-pairs-without-call-id"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
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
            retained_recent_message_count=1,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    tool_items = [item for item in response.json()["timeline_items"] if item["kind"] == "tool"]
    assert len(tool_items) == 2
    assert [item["tool"]["input_payload"] for item in tool_items] == [{"page": 1}, {"page": 2}]
    assert [item["tool"]["output_payload"] for item in tool_items] == [{"total": 1}, {"total": 2}]
    assert all(item["tool"]["tool_call_id"] is None for item in tool_items)

async def test_ai_runtime_timeline_should_interleave_message_fallback_with_tool_events(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """刷新恢复时应按 run 事件轴合并 messages fallback，避免 tool/thinking/message 分桶堆叠。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 时间线顺序工作空间")
    run_id = "run-interleaved-timeline"
    session_id = "session-interleaved-timeline"
    ask_user_tool = {
        "tool_call_id": "tool-ask-1",
        "tool_name": "ask_user",
        "tool_args": {"question": "是否继续整理资源？"},
        "requires_user_input": True,
        "user_feedback_schema": [
            {
                "question": "是否继续整理资源？",
                "header": "继续",
                "options": [
                    {"label": "继续", "description": "继续整理资源。"},
                    {"label": "停止", "description": "停止当前任务。"},
                ],
                "multi_select": False,
            }
        ],
    }
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "时间线顺序会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="检查资源后再问我要不要继续"),
                    Message(role="assistant", content="我先读取资源。", reasoning_content="先确认资源范围。"),
                    Message(
                        role="tool",
                        content='{"total": 2}',
                        tool_name="list_workspace_render_assets",
                        tool_call_id="tool-assets-1",
                        tool_args={"workspace_id": workspace_id},
                    ),
                    Message(role="assistant", content="资源已读取，接下来确认下一步。"),
                ],
                events=[
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-1",
                            "tool_args": {"workspace_id": workspace_id},
                        },
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-1",
                            "result": {"total": 2},
                        },
                    },
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": ask_user_tool,
                    },
                    {
                        "event": "RunPaused",
                        "run_id": run_id,
                        "session_id": session_id,
                        "requirements": [{"id": "req-ask-1", "tool_execution": ask_user_tool}],
                        "tools": [ask_user_tool],
                    },
                ],
                status=RunStatus.paused,
                tools=[ToolExecution.from_dict(ask_user_tool)],
                requirements=[RunRequirement(tool_execution=ToolExecution.from_dict(ask_user_tool))],
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-interleaved-timeline"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
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
            retained_recent_message_count=4,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    timeline_items = response.json()["timeline_items"]
    assert [item["order_index"] for item in timeline_items] == list(range(len(timeline_items)))
    assert [
        (item["kind"], item["role"], item["content"], item["tool"]["tool_name"] if item["tool"] else None)
        for item in timeline_items
    ] == [
        ("message", "user", "检查资源后再问我要不要继续", None),
        ("reasoning", None, "先确认资源范围。", None),
        ("message", "assistant", "我先读取资源。", None),
        ("tool", None, None, "list_workspace_render_assets"),
        ("message", "assistant", "资源已读取，接下来确认下一步。", None),
        ("tool", None, None, "ask_user"),
        ("requirement", None, "是否继续整理资源？", None),
        ("run_status", None, "等待用户处理。", None),
    ]

async def test_ai_runtime_timeline_should_anchor_answered_ask_user_to_pause_event(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """已回答的 ask_user 应回锚到暂停位置，不应在完成后保留 pending requirement 或堆到尾部。"""

    workspace_id = await _create_workspace(authenticated_client, "AI ask_user 回锚工作空间")
    run_id = "run-answered-ask-user-timeline"
    session_id = "session-answered-ask-user-timeline"
    ask_user_questions = [
        {
            "question": "请为这个甘特图组件指定一个中文名称？",
            "header": "组件名称",
            "options": [
                {"label": "项目甘特图", "description": "适用于项目管理场景。"},
                {"label": "任务甘特图", "description": "适用于任务排期场景。"},
            ],
            "multi_select": False,
        }
    ]
    ask_user_tool = {
        "tool_call_id": "call-ask-user-1",
        "tool_name": "ask_user",
        "tool_args": {"questions": ask_user_questions},
        "requires_user_input": True,
        "user_feedback_schema": ask_user_questions,
    }
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "ask_user 回锚会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="创建甘特图"),
                    Message(
                        role="tool",
                        content='User feedback received: [{"question": "请为这个甘特图组件指定一个中文名称？", "selected": ["任务甘特图"]}]',
                        tool_name="ask_user",
                        tool_call_id="call-ask-user-1",
                        tool_args={"questions": ask_user_questions},
                    ),
                    Message(role="assistant", content="已按任务甘特图继续创建。"),
                ],
                events=[
                    {
                        "event": "RunPaused",
                        "run_id": run_id,
                        "session_id": session_id,
                        "requirements": [{"id": "req-ask-user-1", "tool_execution": ask_user_tool}],
                        "tools": [ask_user_tool],
                    },
                    {
                        "event": "RunContent",
                        "run_id": run_id,
                        "content": "已按任务甘特图继续创建。",
                    },
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-answered-ask-user-timeline"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return AgentContextStatusItem(
            session_id=session_id,
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
            retained_recent_message_count=3,
        )

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    timeline_items = response.json()["timeline_items"]
    assert not any(item["kind"] == "requirement" for item in timeline_items)
    ask_user_items = [item for item in timeline_items if item["tool"] and item["tool"]["tool_name"] == "ask_user"]
    assert len(ask_user_items) == 1
    assert ask_user_items[0]["event_index"] == 0
    assert ask_user_items[0]["status"] == "completed"
    assert ask_user_items[0]["tool"]["output_payload"].startswith("User feedback received")
    assert [item["kind"] for item in timeline_items] == ["message", "tool", "message", "run_status"]

async def test_ai_session_stream_should_reject_second_active_run_in_same_session(authenticated_client: AsyncClient) -> None:
    """同一 Agno session 已存在非终态 run 时，应拒绝启动新 run。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Session 串行工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Session 串行项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Session 串行页面",
        content="<template><div>draft</div></template>",
    )

    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Session 串行会话",
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

    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-active-session",
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
        ),
    )

    second_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "同会话第二个 run"},
    )
    assert second_response.status_code == 409
    assert second_response.json()["code"] == "AI_SESSION_RUN_ACTIVE"

async def test_ai_session_stream_should_allow_different_session_when_another_session_is_running(authenticated_client: AsyncClient) -> None:
    """一个 session 的 active run 不应阻塞另一个 session 发起 run。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Session 并行工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Session 并行项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Session 并行页面",
        content="<template><div>draft</div></template>",
    )

    session_ids: list[str] = []
    for index in range(2):
        session_response = await authenticated_client.post(
            "/api/ai/sessions",
            json={
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
                "session_name": f"后台并行会话 {index}",
                "scope": {
                    "workspace_id": workspace_id,
                    "project_id": project_id,
                    "page_id": page_id,
                    "source": "editor-page-detail",
                },
            },
        )
        assert session_response.status_code == 201
        session_ids.append(session_response.json()["session_id"])

    await _append_test_run(
        authenticated_client,
        session_id=session_ids[0],
        run=RunOutput(
            run_id="run-other-session",
            session_id=session_ids[0],
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_ids[1]}/runs/stream",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
        json={"message": "另一个 session 可以启动"},
    )
    assert response.status_code == 200
    assert "AI_LLM_SLOT_UNBOUND" in response.text

async def test_ai_run_stream_should_refresh_context_status_at_message_checkpoints() -> None:
    """长 run 中内容完成和工具完成检查点应推送包含临时历史的上下文状态。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    session_id = "session-checkpoint-1"
    run_id = "run-checkpoint-1"
    agent_id = AGENT_COORDINATOR_AGENT_ID
    scope = AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar")
    runtime_context = AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar")
    snapshots: list[list[tuple[str | None, object, str | None]]] = []

    async def fake_ensure_session_access(**_: object) -> object:
        return SimpleNamespace(metadata={})

    async def fake_context_status_event(**kwargs: object) -> AgentRunEvent:
        extra_history = list(kwargs.get("extra_history_messages") or [])
        snapshots.append([
            (
                getattr(message, "role", None),
                getattr(message, "content", None),
                getattr(message, "tool_name", None),
            )
            for message in extra_history
        ])
        return AgentRunEvent(
            event="context.status",
            run_id=str(kwargs.get("run_id") or ""),
            session_id=session_id,
            data={"message_count": len(extra_history)},
        )

    async def checkpoint_stream():
        yield {"event": "RunStarted", "run_id": run_id, "session_id": session_id, "agent_id": agent_id}
        yield {"event": "RunContent", "run_id": run_id, "session_id": session_id, "content": "第一段回复"}
        yield {"event": "RunContentCompleted", "run_id": run_id, "session_id": session_id, "content": "第一段回复"}
        yield {
            "event": "ToolCallStarted",
            "run_id": run_id,
            "session_id": session_id,
            "tool": {
                "tool_name": "list_workspace_components",
                "tool_call_id": "tool-call-1",
                "tool_args": {"workspace_id": 1},
            },
        }
        yield {
            "event": "ToolCallCompleted",
            "run_id": run_id,
            "session_id": session_id,
            "content": "list_workspace_components completed.",
            "tool": {
                "tool_name": "list_workspace_components",
                "tool_call_id": "tool-call-1",
                "result": {"total": 2},
            },
        }
        yield {"event": "RunCompleted", "run_id": run_id, "session_id": session_id, "content": "最终回复"}

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=checkpoint_stream(), run_id=run_id)

    facade.ensure_session_access = fake_ensure_session_access
    facade._build_context_status_event = fake_context_status_event

    events = [
        event
        async for event in facade._stream_agno_events(
            agent_id=agent_id,
            session_id=session_id,
            scope=scope,
            runtime_context=runtime_context,
            initial_history_messages=[SimpleNamespace(role="user", content="开始")],
            stream_builder=fake_stream_builder,
        )
    ]

    assert [event.event for event in events] == [
        "context.status",
        "run.started",
        "message.delta",
        "context.status",
        "tool.started",
        "tool.completed",
        "context.status",
        "context.status",
        "run.completed",
    ]
    assert snapshots[0] == [("user", "开始", None)]
    assert ("assistant", "第一段回复", None) in snapshots[1]
    assert ("tool", {"total": 2}, "list_workspace_components") in snapshots[2]
    assert ("assistant", "最终回复", None) in snapshots[3]
