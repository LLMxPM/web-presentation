"""文件功能：承载 AI pause resume 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_ai_paused_session_messages_should_be_visible(authenticated_client: AsyncClient, monkeypatch) -> None:
    """写页面导致 run 暂停时，消息历史仍应可被前端重新读取。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 暂停消息工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 暂停消息项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 暂停消息页面",
        content="<template><div>draft</div></template>",
    )

    paused_session = AgentSession(
        session_id="paused-session-1",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "暂停会话"},
        metadata={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "source": "editor-page-detail",
        },
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id="run-paused-1",
                session_id="paused-session-1",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="帮我替换页面图标"),
                    Message(role="assistant", content="我先查看页面内容并生成 diff。"),
                ],
                status=RunStatus.paused,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "paused-session-1"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.page_id == page_id
        return paused_session

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)

    response = await authenticated_client.get(
        "/api/ai/sessions/paused-session-1/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200
    expected_created_at = datetime.fromtimestamp(paused_session.runs[0].messages[0].created_at, tz=UTC).isoformat()
    assert response.json() == [
            {
                "id": paused_session.runs[0].messages[0].id,
                "run_id": "run-paused-1",
                "role": "user",
            "content": "帮我替换页面图标",
            "reasoning_content": None,
            "created_at": expected_created_at,
            "tool_name": None,
            "tool_call_id": None,
            "tool_args": None,
            "tool_call_error": None,
            "tool_calls": [],
            "attachments": [],
        },
            {
                "id": paused_session.runs[0].messages[1].id,
                "run_id": "run-paused-1",
                "role": "assistant",
            "content": "我先查看页面内容并生成 diff。",
            "reasoning_content": None,
            "created_at": expected_created_at,
            "tool_name": None,
            "tool_call_id": None,
            "tool_args": None,
            "tool_call_error": None,
            "tool_calls": [],
            "attachments": [],
        },
    ]

async def test_ai_raw_continue_exception_should_mark_resolved_confirmation_error() -> None:
    """continue raw SSE 异常时，应按已提交确认清理目标 run 并返回带 run_id 的错误事件。"""

    async def fake_stream_builder() -> SimpleNamespace:
        raise AppException(status_code=500, code="AI_FAKE_CONTINUE_FAILED", detail="继续执行失败")

    marked_payloads: list[dict[str, object]] = []
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._get_session_run_lock = lambda **_: asyncio.Lock()
    facade.ensure_session_access = lambda **_: _async_value(SimpleNamespace(metadata={}))

    async def fake_mark_terminal(**kwargs: object) -> None:
        marked_payloads.append(dict(kwargs))

    facade._mark_run_terminal = fake_mark_terminal

    chunks = [
        chunk
        async for chunk in facade._stream_agno_raw_sse(
            session_id="session-raw-continue-error",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
            fallback_user_message=None,
            expected_run_id="run-raw-continue-error",
            resolved_tool_execution={
                "tool_call_id": "tool-confirm-error",
                "tool_name": "apply_page_edits",
                "confirmed": True,
            },
            stream_builder=fake_stream_builder,
        )
    ]

    event_payloads = [
        json.loads(line.removeprefix("data: "))
        for chunk in chunks
        for line in chunk.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert event_payloads[0]["run_id"] == "run-raw-continue-error"
    assert event_payloads[0]["error_type"] == "AI_FAKE_CONTINUE_FAILED"
    assert marked_payloads[0]["run_id"] == "run-raw-continue-error"
    assert marked_payloads[0]["status"] == RunStatus.error
    assert marked_payloads[0]["resolved_tool_execution"]["tool_call_id"] == "tool-confirm-error"

async def test_ai_raw_sse_should_stop_and_release_lock_after_pause_event() -> None:
    """raw SSE 收到暂停事件后应收束本轮流，避免 HITL 提交后保持 loading。"""

    run_id = f"run-raw-pause-{uuid4()}"
    session_id = f"session-raw-pause-{uuid4()}"
    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    facade.ensure_session_access = lambda **_: _async_value(AgentSession(session_id=session_id, agent_id=COMPONENT_MANAGER_AGENT_ID, user_id="1"))
    marked_payloads: list[dict[str, object]] = []
    preserve_payloads: list[dict[str, object]] = []

    async def fake_set_existing_run_status(**kwargs: object) -> None:
        marked_payloads.append(dict(kwargs))

    async def fake_preserve_cancelled_raw_run_messages(**kwargs: object) -> None:
        preserve_payloads.append(dict(kwargs))
        return None

    async def paused_then_waits():
        payload = {
            "event": "RunPaused",
            "run_id": run_id,
            "session_id": session_id,
            "requirements": [
                {
                    "id": "req-raw-pause",
                    "tool_execution": {
                        "tool_call_id": "tool-raw-pause",
                        "tool_name": "ask_user",
                        "requires_user_input": True,
                        "user_feedback_schema": [
                            {
                                "question": "是否继续？",
                                "header": "继续",
                                "options": [{"label": "继续"}, {"label": "停止"}],
                                "multi_select": False,
                            }
                        ],
                    },
                }
            ],
        }
        yield f"event: RunPaused\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        await asyncio.Event().wait()

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=paused_then_waits(), run_id=run_id)

    facade._set_existing_run_status = fake_set_existing_run_status
    facade._preserve_cancelled_raw_run_messages = fake_preserve_cancelled_raw_run_messages
    lock = facade._get_session_run_lock(session_id=session_id, agent_id=COMPONENT_MANAGER_AGENT_ID)

    chunks = await asyncio.wait_for(
        _collect_chunks(
            facade._stream_agno_raw_sse(
                session_id=session_id,
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-component-library"),
                stream_builder=fake_stream_builder,
            )
        ),
        timeout=1,
    )
    parsed_events = [parsed for chunk in chunks for parsed in _iter_raw_sse_payloads(chunk)]

    assert [(event_name, payload.get("run_id")) for payload, event_name in parsed_events] == [("RunPaused", run_id)]
    assert marked_payloads[0]["run_id"] == run_id
    assert marked_payloads[0]["status"] == RunStatus.paused
    assert preserve_payloads == []
    assert not lock.locked()

async def test_ai_run_output_with_pending_feedback_should_be_normalized_as_paused() -> None:
    """RunOutput 即使被 Agno 标记完成，未解决 ask_user requirement 仍应恢复为暂停态。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    runtime_context = AgentRuntimeContext(
        scope_type="workspace",
        workspace_id=1,
        source="editor-component-library",
    )
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-1",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "这次优先调整哪个区域？",
                    "header": "范围",
                    "options": [
                        {"label": "首屏", "description": "只调整第一屏。"},
                        {"label": "全页面", "description": "整体调整。"},
                    ],
                    "multi_select": False,
                }
            ],
        }
    )

    event = facade._normalize_event(
        raw_event=RunOutput(
            run_id="run-feedback-paused",
            session_id="session-feedback-paused",
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.completed,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
        runtime_context=runtime_context,
        session_id="session-feedback-paused",
    )

    assert event is not None
    assert event.event == "run.paused"
    requirement = event.data["requirement"]
    assert requirement["kind"] == "user_feedback"
    assert requirement["tool_name"] == "ask_user"
    assert requirement["user_feedback_schema"][0]["question"] == "这次优先调整哪个区域？"

async def test_extract_pending_requirement_should_fallback_to_paused_tools() -> None:
    """RunPaused 若未携带 requirements，也应能从 tools 兜底出确认动作。"""

    current_page = _build_page_item(page_id=31, content="<template><div>old</div></template>\n")

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-paused-tools-only",
            "session_id": "session-tools-only",
            "tools": [
                {
                    "tool_call_id": "tool-1",
                    "tool_name": "apply_page_edits",
                    "requires_confirmation": True,
                    "tool_args": {
                        "edits": [
                            {
                                "type": "replace_exact",
                                "old_text": "<template><div>old</div></template>",
                                "new_text": "<template><div>new</div></template>",
                            }
                        ],
                        "change_note": "替换页面内容",
                    },
                }
            ],
        },
        current_page=current_page,
    )

    assert requirement is not None
    assert requirement.run_id == "run-paused-tools-only"
    assert requirement.session_id == "session-tools-only"
    assert requirement.tool_name == "apply_page_edits"
    assert requirement.suggested_patch is not None
    assert requirement.suggested_patch.proposed_content == "<template><div>new</div></template>\n"
    assert requirement.suggested_patch.change_note == "替换页面内容"

async def test_extract_pending_requirement_should_keep_pause_when_edits_preview_fails() -> None:
    """edits 预览生成失败时，不应吞掉暂停动作，而应返回可提示前端的 note。"""

    current_page = _build_page_item(page_id=32, content="<template><div>old</div></template>")

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-paused-bad-edits",
            "session_id": "session-bad-edits",
            "requirements": [
                {
                    "id": "requirement-1",
                    "tool_execution": {
                        "tool_call_id": "tool-bad",
                        "tool_name": "apply_page_edits",
                        "requires_confirmation": True,
                        "tool_args": {
                            "edits": [
                                {
                                    "type": "replace_exact",
                                    "old_text": "<template><div>missing</div></template>",
                                    "new_text": "<template><div>new</div></template>",
                                }
                            ],
                            "change_note": "错误 edits 预览",
                        },
                    },
                }
            ],
        },
        current_page=current_page,
    )

    assert requirement is not None
    assert requirement.tool_name == "apply_page_edits"
    assert requirement.suggested_patch is None
    assert requirement.note is not None
    assert "无法预生成 edits 预览" in requirement.note

async def test_extract_pending_requirement_should_build_canonical_diff_from_edits() -> None:
    """暂停态若拿到 edits，应下发后端生成的 canonical diff 给前端确认。"""

    current_page = _build_page_item(page_id=66, content="alpha\nbeta\ngamma\ndelta\n")

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-paused-edits",
            "session_id": "session-edits",
            "requirements": [
                {
                    "id": "requirement-edits",
                    "tool_execution": {
                        "tool_call_id": "tool-edits",
                        "tool_name": "apply_page_edits",
                        "requires_confirmation": True,
                        "tool_args": {
                            "edits": [{"type": "replace_exact", "old_text": "delta\n", "new_text": "zeta\n"}],
                            "change_note": "修正发展愿景描述",
                        },
                    },
                }
            ],
        },
        current_page=current_page,
    )

    assert requirement is not None
    assert requirement.suggested_patch is not None
    assert requirement.suggested_patch.proposed_content == "alpha\nbeta\ngamma\nzeta\n"
    assert requirement.suggested_patch.unified_diff.startswith("--- current\n+++ proposed\n@@ ")
    assert "-delta\n+zeta\n" in requirement.suggested_patch.unified_diff
    assert "edits" in requirement.tool_execution["tool_args"]

async def test_extract_pending_requirement_should_support_user_feedback_questions() -> None:
    """ask_user 暂停态应被提取为结构化提问，并强制按单选下发。"""

    requirement = _extract_pending_requirement(
        payload={
            "run_id": "run-feedback",
            "session_id": "session-feedback",
            "requirements": [
                {
                    "id": "requirement-feedback",
                    "tool_execution": {
                        "tool_call_id": "tool-ask",
                        "tool_name": "ask_user",
                        "tool_args": {},
                        "requires_user_input": True,
                    },
                    "user_feedback_schema": [
                        {
                            "question": "这次优先调整哪个区域？",
                            "header": "范围",
                            "multi_select": True,
                            "options": [
                                {"label": "首屏", "description": "只调整第一屏。"},
                                {"label": "全页面", "description": "整体调整。"},
                            ],
                        },
                        {
                            "question": "视觉风格倾向是什么？",
                            "header": "风格",
                            "options": [
                                {"label": "克制"},
                                {"label": "醒目"},
                            ],
                        },
                    ],
                }
            ],
        },
        runtime_context=AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
    )

    assert requirement is not None
    assert requirement.kind == "user_feedback"
    assert requirement.tool_name == "ask_user"
    assert len(requirement.user_feedback_schema) == 2
    assert requirement.user_feedback_schema[0]["multi_select"] is False
    assert requirement.tool_execution["requires_user_input"] is True
    assert requirement.tool_execution["user_feedback_schema"][0]["question"] == "这次优先调整哪个区域？"

def test_apply_user_feedback_selections_should_write_preset_and_custom_answers() -> None:
    """继续 ask_user 时，应把预设选项和自定义回答都写回 Agno ToolExecution。"""

    updated = _apply_user_feedback_selections(
        {
            "tool_name": "ask_user",
            "tool_call_id": "tool-ask",
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "这次优先调整哪个区域？",
                    "header": "范围",
                    "multi_select": False,
                    "options": [
                        {"label": "首屏", "description": "只调整第一屏。"},
                        {"label": "全页面", "description": "整体调整。"},
                    ],
                },
                {
                    "question": "视觉风格倾向是什么？",
                    "header": "风格",
                    "multi_select": False,
                    "options": [
                        {"label": "克制"},
                        {"label": "醒目"},
                    ],
                },
            ],
        },
        [
            {"question": "这次优先调整哪个区域？", "selected_label": "首屏", "custom_text": None},
            {"question": "视觉风格倾向是什么？", "selected_label": None, "custom_text": "保留当前图标风格"},
        ],
    )

    assert updated["requires_user_input"] is True
    assert updated["answered"] is True
    assert updated["user_feedback_schema"][0]["selected_options"] == ["首屏"]
    assert updated["user_feedback_schema"][0]["options"][0]["selected"] is True
    assert updated["user_feedback_schema"][1]["selected_options"] == ["用户补充：保留当前图标风格"]
    assert all(option["selected"] is False for option in updated["user_feedback_schema"][1]["options"])
    requirement = _build_run_requirement_from_tool_execution_payload(updated)
    assert requirement.tool_execution is not None
    assert requirement.tool_execution.answered is True
    assert requirement.tool_execution.requires_user_input is False
    assert requirement.tool_execution.external_execution_required is True
    assert requirement.tool_execution.result is not None
    assert "首屏" in requirement.tool_execution.result
    assert "保留当前图标风格" in requirement.tool_execution.result
    assert requirement.external_execution_result == requirement.tool_execution.result
    assert requirement.is_resolved() is True

async def test_ai_session_active_run_should_return_paused_requirement(authenticated_client: AsyncClient) -> None:
    """active-run 应从 Agno session.runs 读取 paused 状态并提取待确认动作。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Active Run 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Active Run 项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Active Run 页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Active Run 会话",
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
            run_id="run-paused-active",
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.paused,
            tools=[
                ToolExecution.from_dict(
                    {
                        "tool_name": "apply_page_edits",
                        "tool_call_id": "tool-confirm-1",
                        "tool_args": {
                            "change_note": "测试确认",
                            "edits": [{"type": "replace_exact", "old_text": "draft", "new_text": "done"}],
                            "base_version_no": 1,
                        },
                        "requires_confirmation": True,
                    }
                )
            ],
        ),
    )

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-paused-active"
    assert payload["status"] == "paused"
    assert payload["pending_requirement"]["tool_name"] == "apply_page_edits"
    assert payload["pending_requirement"]["tool_execution"]["tool_call_id"] == "tool-confirm-1"

async def test_ai_force_cancel_paused_confirmation_should_release_hitl(authenticated_client: AsyncClient) -> None:
    """强制释放工具确认 HITL 时，应取消 run 并清理确认 requirement。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Force Confirm 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Force Confirm 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    confirm_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-force-confirm",
            "tool_name": "delete_component",
            "tool_args": {"component_id": 1},
            "requires_confirmation": True,
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-force-confirm",
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[confirm_tool],
            requirements=[RunRequirement(tool_execution=confirm_tool)],
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
        json={"force": True, "tool_call_id": "tool-force-confirm"},
    )
    assert response.status_code == 200, response.text

    active_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )
    assert active_response.status_code == 200
    assert active_response.json() is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    run = session_model.get_run("run-force-confirm")
    assert run is not None
    assert run.status == RunStatus.cancelled
    assert not run.requirements
    assert run.tools[0].requires_confirmation is False
    assert run.tools[0].confirmed is False

async def test_ai_force_cancel_paused_feedback_should_release_hitl(authenticated_client: AsyncClient) -> None:
    """强制释放结构化提问 HITL 时，应取消 run 并清理回答 requirement。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Force Feedback 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Force Feedback 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-force-feedback",
            "tool_name": "ask_user",
            "tool_args": {},
            "requires_user_input": True,
            "user_feedback_schema": [
                {
                    "question": "优先调整哪个区域？",
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
            run_id="run-force-feedback",
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[ask_user_tool],
            requirements=[RunRequirement(tool_execution=ask_user_tool)],
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
        json={"force": True, "tool_call_id": "tool-force-feedback"},
    )
    assert response.status_code == 200, response.text

    active_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )
    assert active_response.status_code == 200
    assert active_response.json() is None

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_model = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.AGENT, "1", True)
    assert isinstance(session_model, AgentSession)
    run = session_model.get_run("run-force-feedback")
    assert run is not None
    assert run.status == RunStatus.cancelled
    assert not run.requirements
    assert run.tools[0].requires_user_input is False
    assert run.tools[0].answered is False

async def test_ai_force_cancel_paused_requirement_should_reject_stale_tool_call(
    authenticated_client: AsyncClient,
) -> None:
    """强制释放 HITL 时若 tool_call_id 已变化，应拒绝请求并保留原暂停态。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Force Stale 工作空间")
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
            "session_name": "Force Stale 会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-component-library",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    confirm_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-force-current",
            "tool_name": "delete_component",
            "tool_args": {"component_id": 1},
            "requires_confirmation": True,
        }
    )
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id="run-force-stale",
            session_id=session_id,
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            status=RunStatus.paused,
            tools=[confirm_tool],
            requirements=[RunRequirement(tool_execution=confirm_tool)],
        ),
    )

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/active-run/cancel",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
        json={"force": True, "tool_call_id": "tool-force-old"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "AI_RUN_REQUIREMENT_STALE"

    active_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/active-run",
        params={
            "workspace_id": workspace_id,
            "scope_type": "workspace",
            "source": "editor-component-library",
            "agent_id": COMPONENT_MANAGER_AGENT_ID,
        },
    )
    assert active_response.status_code == 200
    payload = active_response.json()
    assert payload["status"] == "paused"
    assert payload["pending_requirement"]["tool_execution"]["tool_call_id"] == "tool-force-current"

async def test_ai_session_runtime_should_ignore_binary_images_in_active_run(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """runtime 快照恢复 active-run 时不应把历史图片 bytes 当 UTF-8 序列化。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Active Run 图片工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Active Run 图片项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Active Run 图片页面",
        content="<template><div>image</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Active Run 图片会话",
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
            run_id="run-active-image-bytes",
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
            messages=[
                Message(
                    role="user",
                    content="请分析这张图",
                    images=[Image(content=b"\x89PNG\r\n\x1a\n", mime_type="image/png", detail="auto")],
                )
            ],
        ),
    )

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

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["active_run"]["run_id"] == "run-active-image-bytes"
    assert payload["active_run"]["status"] == "running"
    assert payload["timeline_items"][0]["content"] == "请分析这张图"

async def test_ai_continue_active_events_should_accept_pending_requirement_on_failed_agno_run(monkeypatch) -> None:
    """Agno run 状态为 error 但 requirement 未解决时，continue 不应报没有暂停运行。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    ask_user_tool = ToolExecution.from_dict(
        {
            "tool_call_id": "tool-ask-continue",
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
    session_detail = AgentSession(
        session_id="continue-feedback-session",
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        user_id="1",
        metadata={"workspace_id": 1, "source": "editor-component-library"},
        runs=[
            RunOutput(
                run_id="continue-feedback-run",
                session_id="continue-feedback-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.error,
                tools=[ask_user_tool],
                requirements=[RunRequirement(tool_execution=ask_user_tool)],
            )
        ],
    )
    captured: dict[str, object] = {}

    async def fake_ensure_session_access(**_: object) -> AgentSession:
        return session_detail

    async def fake_build_agent_runtime_context(**_: object) -> AgentRuntimeContext:
        return AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-component-library")

    async def fake_continue_events(**kwargs: object):
        captured.update(kwargs)
        yield AgentRunEvent(
            event="run.continued",
            run_id="continue-feedback-run",
            session_id="continue-feedback-session",
            data={},
        )

    facade.ensure_session_access = fake_ensure_session_access
    facade.continue_events = fake_continue_events
    facade._session = SimpleNamespace()
    monkeypatch.setattr("app.ai.session_facade.build_agent_runtime_context", fake_build_agent_runtime_context)

    events = [
        event async for event in facade.continue_active_events(
            session_id="continue-feedback-session",
            agent_id=COMPONENT_MANAGER_AGENT_ID,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-component-library"),
            tool_execution={
                "tool_call_id": "tool-ask-continue",
                "tool_name": "ask_user",
            },
            decision=None,
            note=None,
            feedback_selections=[
                {
                    "question": "组件 default slot 的默认内容应如何处理？",
                    "selected_label": "完全清空",
                    "custom_text": None,
                }
            ],
            runtime_context=AgentRuntimeContext(
                scope_type="workspace",
                workspace_id=1,
                source="editor-component-library",
            ),
        )
    ]

    assert [event.event for event in events] == ["run.continued"]
    assert captured["run_id"] == "continue-feedback-run"
    merged_tool_execution = captured["tool_execution"]
    assert isinstance(merged_tool_execution, dict)
    assert merged_tool_execution["tool_call_id"] == "tool-ask-continue"
    assert merged_tool_execution["requires_user_input"] is True
    assert len(merged_tool_execution["user_feedback_schema"]) == 1

async def test_ai_stream_should_release_session_lock_after_pause_event() -> None:
    """后台流收到 run.paused 后应主动收束，避免待确认 run 长时间占住会话锁。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    session_id = f"pause-lock-session-{uuid4()}"
    run_id = f"pause-lock-run-{uuid4()}"
    agent_id = COMPONENT_MANAGER_AGENT_ID
    scope = AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-component-library")
    runtime_context = AgentRuntimeContext(scope_type="workspace", workspace_id=1, source="editor-component-library")
    pause_payload = {
        "event": "RunPaused",
        "run_id": run_id,
        "session_id": session_id,
        "requirements": [
            {
                "tool_execution": {
                    "tool_call_id": "tool-pause-lock",
                    "tool_name": "delete_component",
                    "tool_args": {"component_id": 1},
                    "requires_confirmation": True,
                },
            }
        ],
    }

    async def fake_ensure_session_access(**_: object) -> object:
        return SimpleNamespace(metadata={})

    async def fake_context_status_event(**kwargs: object) -> AgentRunEvent:
        return AgentRunEvent(
            event="context.status",
            run_id=str(kwargs.get("run_id") or ""),
            session_id=session_id,
            data={},
        )

    async def paused_then_never_finishes():
        yield pause_payload
        await asyncio.Event().wait()

    async def fake_stream_builder() -> SimpleNamespace:
        return SimpleNamespace(agent=SimpleNamespace(), stream=paused_then_never_finishes(), run_id=run_id)

    facade.ensure_session_access = fake_ensure_session_access
    facade._build_context_status_event = fake_context_status_event
    lock = facade._get_session_run_lock(session_id=session_id, agent_id=agent_id)

    async def collect_events() -> list[AgentRunEvent]:
        return [
            event
            async for event in facade._stream_agno_events(
                agent_id=agent_id,
                session_id=session_id,
                scope=scope,
                runtime_context=runtime_context,
                stream_builder=fake_stream_builder,
            )
        ]

    events = await asyncio.wait_for(collect_events(), timeout=1)

    assert [event.event for event in events] == ["context.status", "context.status", "run.paused"]
    assert not lock.locked()

def test_ai_resolve_requirement_payload_should_use_latest_active_requirement() -> None:
    """连续 HITL 暂停时应展示最新未处理动作，避免把旧 tool_call_id 再次提交给 Agno。"""

    requirement = _resolve_requirement_payload(
        {
            "requirements": [
                {
                    "id": "old-requirement",
                    "tool_execution": {
                        "tool_call_id": "call-old",
                        "tool_name": "apply_component_edits",
                        "requires_confirmation": True,
                    },
                },
                {
                    "id": "new-requirement",
                    "tool_execution": {
                        "tool_call_id": "call-new",
                        "tool_name": "update_component_metadata",
                        "requires_confirmation": True,
                    },
                },
            ],
        }
    )

    assert requirement is not None
    assert requirement["id"] == "new-requirement"
    assert requirement["tool_execution"]["tool_call_id"] == "call-new"
