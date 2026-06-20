"""文件功能：用 Pydantic AI 本地流式模型验证平台 runner 的真实事件投影与 ask_user 闭环。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic_ai import Agent, DeferredToolResults
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    ModelMessagesTypeAdapter,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, DeltaToolCall, FunctionModel
from pydantic_ai.tools import DeferredToolRequests, Tool
from pydantic_ai.usage import RequestUsage
from sqlalchemy import select

from app.ai.agent.runtime_context import AgentRuntimeContext
from app.ai.message_history import build_history_budget
from app.ai.platform_tools import AgentToolContext, agent_tool
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.pydantic_event_projection import PydanticEventProjector
from app.ai.pydantic_runner import PydanticAgentRunner, _requirement_from_deferred
from app.ai.pydantic_tools import AgentToolDeps, _wrap_platform_tool
from app.ai.session_facade_pydantic import _build_continue_message_history, _build_deferred_results
from app.ai.tools.team_delegation import build_team_delegation_tools
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentRunEvent, AiAgentToolCall
from app.schemas.agent import AgentScopeContext


async def test_pydantic_runner_should_pause_continue_and_replay_ask_user(
    authenticated_client: AsyncClient,
) -> None:
    """真实 Pydantic AI 流式事件应能完成 ask_user 暂停、回答、继续和快照回放闭环。"""

    workspace_id, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner ask_user 工作空间",
        session_name="Pydantic Runner ask_user 会话",
    )
    model = FunctionModel(stream_function=_ask_user_stream_function)
    tools = [Tool(_ask_user_tool, name="ask_user", requires_approval=True)]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-ask-user",
            message="请根据需要询问我。",
            image_attachment_ids=[],
        )
        runner = PydanticAgentRunner(store)

        first_events = await _collect_runner_events(
            runner.stream_run(
                run_model=run_start.run_model,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="请根据需要询问我。",
                tools=tools,
            )
        )

        latest_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert latest_run is not None
        assert latest_run.status == "paused"
        assert latest_run.message_history_json
        assert [event.event for event in first_events] == [
            "model.request.started",
            "reasoning.delta",
            "message.delta",
            "model.request.completed",
            "tool.started",
            "run.paused",
        ]
        requirement = await store.get_pending_requirement(run_id=latest_run.run_id)
        assert requirement is not None
        assert requirement.kind == "user_feedback"
        assert requirement.tool_call_id == "tool-ask-layout"
        assert requirement.payload_json["user_feedback_schema"][0]["question"] == "页面应优先调整哪个区域？"

        await store.resolve_requirement(
            requirement,
            payload={
                "feedback_selections": [
                    {
                        "question": "页面应优先调整哪个区域？",
                        "selected_label": "首屏",
                        "custom_text": None,
                    }
                ]
            },
        )
        latest_run.status = "running"
        latest_run.pending_requirement_json = None
        await store.append_event(
            latest_run,
            first_events[0].model_copy(update={"event": "run.continued", "content": None, "data": {}}),
        )
        deferred_results = _build_deferred_results(
            requirement_tool_call_id="tool-ask-layout",
            decision="confirm",
            note=None,
            tool_execution={
                "tool_name": "ask_user",
                "tool_call_id": "tool-ask-layout",
                "tool_args": {
                    "questions": [
                        {
                            "question": "页面应优先调整哪个区域？",
                            "options": [{"label": "首屏"}, {"label": "全页面"}],
                        }
                    ]
                },
            },
            feedback_selections=[
                {
                    "question": "页面应优先调整哪个区域？",
                    "selected_label": "首屏",
                    "custom_text": None,
                }
            ],
        )
        continue_history = _build_continue_message_history(
            run_model_message_history=latest_run.message_history_json,
            run_input_payload=latest_run.input_payload_json,
            run_id=latest_run.run_id,
            tool_execution={
                "tool_name": "ask_user",
                "tool_call_id": "tool-ask-layout",
                "tool_args": {
                    "questions": [
                        {
                            "question": "页面应优先调整哪个区域？",
                            "options": [{"label": "首屏"}, {"label": "全页面"}],
                        }
                    ]
                },
            },
        )

        second_events = await _collect_runner_events(
            runner.stream_run(
                run_model=latest_run,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="",
                tools=tools,
                message_history=continue_history,
                deferred_tool_results=deferred_results,
            )
        )

        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert completed_run is not None
        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=_runtime_context(scope),
        )
        result = await db_session.execute(
            select(AiAgentToolCall).where(
                AiAgentToolCall.run_id == completed_run.run_id,
                AiAgentToolCall.tool_call_id == "tool-ask-layout",
            )
        )
        tool_call = result.scalar_one()
        event_names = (
            await db_session.execute(
                select(AiAgentRunEvent.event)
                .where(AiAgentRunEvent.run_id == completed_run.run_id)
                .order_by(AiAgentRunEvent.event_index.asc())
            )
        ).scalars().all()

    assert [event.event for event in second_events] == [
        "tool.started",
        "tool.completed",
        "model.request.started",
        "reasoning.delta",
        "message.delta",
        "model.request.completed",
        "run.completed",
    ]
    assert completed_run.status == "completed"
    assert completed_run.content == "我需要确认页面调整范围。我会优先调整首屏。"
    assert completed_run.reasoning_content == "先确认用户偏好。收到用户反馈。"
    assert tool_call.status == "completed"
    assert tool_call.output_payload_json == (
        'User feedback received: [{"question": "页面应优先调整哪个区域？", "selected": ["首屏"]}]'
    )
    assert event_names == [
        "run.started",
        "model.request.started",
        "reasoning.delta",
        "message.delta",
        "model.request.completed",
        "tool.started",
        "run.paused",
        "run.continued",
        "tool.started",
        "tool.completed",
        "model.request.started",
        "reasoning.delta",
        "message.delta",
        "model.request.completed",
        "run.completed",
    ]
    assert snapshot.last_run is not None
    assert snapshot.last_run.status == "completed"
    assert [item.kind for item in snapshot.timeline_items] == [
        "message",
        "reasoning",
        "message",
        "tool",
        "requirement",
        "reasoning",
        "message",
    ]
    assert workspace_id == scope.workspace_id


async def test_pydantic_runner_should_mark_rejected_approval_tool_error(
    authenticated_client: AsyncClient,
) -> None:
    """人工拒绝确认工具后，平台工具态应保持 error，不能被拒绝回灌覆盖为 completed。"""

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner 拒绝工具工作空间",
        session_name="Pydantic Runner 拒绝工具会话",
    )
    model = FunctionModel(stream_function=_approval_tool_stream_function)
    tools = [Tool(_approval_write_tool, name="dangerous_write", requires_approval=True)]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-reject-approval",
            message="需要确认后写入。",
            image_attachment_ids=[],
        )
        runner = PydanticAgentRunner(store)
        first_events = await _collect_runner_events(
            runner.stream_run(
                run_model=run_start.run_model,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="需要确认后写入。",
                tools=tools,
            )
        )

        latest_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert latest_run is not None
        assert latest_run.status == "paused"
        requirement = await store.get_pending_requirement(run_id=latest_run.run_id)
        assert requirement is not None
        assert requirement.kind == "confirmation"
        assert requirement.tool_call_id == "tool-write-route"

        await store.resolve_requirement(
            requirement,
            payload={
                "decision": "reject",
                "note": None,
                "tool_execution": requirement.payload_json["tool_execution"],
                "feedback_selections": [],
            },
        )
        latest_run.status = "running"
        latest_run.pending_requirement_json = None
        await store.append_event(
            latest_run,
            first_events[0].model_copy(update={"event": "run.continued", "content": None, "data": {}}),
        )
        deferred_results = _build_deferred_results(
            requirement_tool_call_id="tool-write-route",
            decision="reject",
            note=None,
            tool_execution=requirement.payload_json["tool_execution"],
            feedback_selections=[],
        )
        continue_history = _build_continue_message_history(
            run_model_message_history=latest_run.message_history_json,
            run_input_payload=latest_run.input_payload_json,
            run_id=latest_run.run_id,
            tool_execution=requirement.payload_json["tool_execution"],
        )

        second_events = await _collect_runner_events(
            runner.stream_run(
                run_model=latest_run,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="",
                tools=tools,
                message_history=continue_history,
                deferred_tool_results=deferred_results,
            )
        )
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert completed_run is not None
        result = await db_session.execute(
            select(AiAgentToolCall).where(
                AiAgentToolCall.run_id == completed_run.run_id,
                AiAgentToolCall.tool_call_id == "tool-write-route",
            )
        )
        tool_call = result.scalar_one()

    assert [event.event for event in second_events] == [
        "tool.error",
        "model.request.started",
        "message.delta",
        "model.request.completed",
        "run.completed",
    ]
    assert completed_run.status == "completed"
    assert completed_run.content == "已跳过写入。"
    assert tool_call.status == "error"
    assert tool_call.message == "用户拒绝执行该工具。"


async def test_pydantic_runner_should_continue_after_recoverable_tool_error(
    authenticated_client: AsyncClient,
) -> None:
    """普通业务工具错误应写成 tool.error，并把错误返回模型继续完成 run。"""

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner 可恢复工具错误工作空间",
        session_name="Pydantic Runner 可恢复工具错误会话",
    )
    run_id = "pydantic-runner-recoverable-tool-error"
    model = FunctionModel(stream_function=_recoverable_tool_error_stream_function)
    tools = [_wrap_platform_tool(recoverable_error_tool)]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id=run_id,
            message="读取资源并继续。",
            image_attachment_ids=[],
        )

        events = await _collect_runner_events(
            PydanticAgentRunner(store).stream_run(
                run_model=run_start.run_model,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="读取资源并继续。",
                tools=tools,
                deps=AgentToolDeps(dependencies={"run_id": run_id, "session_id": session_id}),
            )
        )
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert completed_run is not None
        tool_call = await db_session.scalar(
            select(AiAgentToolCall).where(
                AiAgentToolCall.run_id == run_id,
                AiAgentToolCall.tool_call_id == "tool-recoverable-read",
            )
        )

    assert completed_run.status == "completed"
    assert completed_run.content == "已换用其他资源继续。"
    assert "tool.error" in [event.event for event in events]
    assert "run.error" not in [event.event for event in events]
    assert events[-1].event == "run.completed"
    assert tool_call is not None
    assert tool_call.status == "error"
    assert tool_call.output_payload_json["kind"] == "recoverable_tool_error"
    assert "ASSET_CONTENT_READ_UNSUPPORTED" in tool_call.message


async def test_pydantic_runner_should_return_member_delegation_result_to_coordinator(
    authenticated_client: AsyncClient,
) -> None:
    """内容助手委派工具应拿到成员结果，并把当前委派 tool_call_id 传给执行器。"""

    _, scope = await _create_workspace_scope(
        authenticated_client,
        workspace_name="Pydantic Runner 成员委派工作空间",
        source="editor-page-detail",
    )
    session_id = "session-pydantic-runner-member-delegation"
    run_id = "pydantic-runner-member-delegation"
    model = FunctionModel(stream_function=_member_delegation_stream_function)
    executor = _FakeMemberDelegationExecutor()
    tools = [
        _wrap_platform_tool(tool_item)
        for tool_item in build_team_delegation_tools(get_session_factory())
    ]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        await store.create_session(
            session_id=session_id,
            agent_id="agent-coordinator",
            session_name="Pydantic Runner 成员委派会话",
            scope=scope,
        )
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id=run_id,
            message="请让资源助手整理封面图资源。",
            image_attachment_ids=[],
        )

        events = await _collect_runner_events(
            PydanticAgentRunner(store).stream_run(
                run_model=run_start.run_model,
                agent_id="agent-coordinator",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="请让资源助手整理封面图资源。",
                tools=tools,
                deps=AgentToolDeps(
                    dependencies={
                        "run_id": run_id,
                        "session_id": session_id,
                        "member_delegation_executor": executor,
                    }
                ),
            )
        )
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="agent-coordinator")
        assert completed_run is not None
        tool_call = await db_session.scalar(
            select(AiAgentToolCall).where(
                AiAgentToolCall.run_id == run_id,
                AiAgentToolCall.tool_call_id == "tool-delegate-resource",
            )
        )

    assert completed_run.status == "completed"
    assert completed_run.content == "已整合资源助手结果。"
    assert executor.calls == [
        {
            "member_id": "resource-manager",
            "task": "整理封面图资源",
            "handoff_context": "页面需要封面视觉资源",
            "expected_output": "返回可引用资源名",
            "delegate_tool_call_id": "tool-delegate-resource",
            "delegate_tool_name": "delegate_task_to_member",
        }
    ]
    assert "tool.completed" in [event.event for event in events]
    assert events[-1].event == "run.completed"
    assert tool_call is not None
    assert tool_call.status == "completed"
    assert tool_call.output_payload_json["member_run_id"] == "member-run-fake-resource"


async def test_pydantic_runner_should_fail_fast_for_bad_ask_user_payload(
    authenticated_client: AsyncClient,
) -> None:
    """模型输出 title/value 等非法 ask_user 参数时，不应进入无法展示的暂停态。"""

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner ask_user 非法参数工作空间",
        session_name="Pydantic Runner ask_user 非法参数会话",
    )
    model = FunctionModel(stream_function=_bad_ask_user_stream_function)
    tools = [Tool(_ask_user_tool, name="ask_user", requires_approval=True)]

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-bad-ask-user",
            message="缺信息就问我。",
            image_attachment_ids=[],
        )
        events = await _collect_runner_events(
            PydanticAgentRunner(store).stream_run(
                run_model=run_start.run_model,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="缺信息就问我。",
                tools=tools,
            )
        )
        latest_run = await db_session.get(AiAgentRun, run_start.run_model.run_id)

    assert latest_run is not None
    assert latest_run.status == "failed"
    assert latest_run.error_code == "AI_ASK_USER_SCHEMA_INVALID"
    assert events[-1].event == "run.error"
    assert "缺少可展示的问题" in (events[-1].data.get("message") or "")


async def test_pydantic_runner_should_buffer_consecutive_delta_chunks(
    authenticated_client: AsyncClient,
) -> None:
    """连续同类文本和思考 delta 应合并为较少的平台事件，但最终内容保持完整。"""

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner delta 缓冲工作空间",
        session_name="Pydantic Runner delta 缓冲会话",
    )
    model = FunctionModel(stream_function=_chunked_delta_stream_function)

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-buffered-delta",
            message="请输出分段内容。",
            image_attachment_ids=[],
        )

        events = await _collect_runner_events(
            PydanticAgentRunner(store).stream_run(
                run_model=run_start.run_model,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="请输出分段内容。",
            )
        )
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert completed_run is not None
        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="component-manager",
            runtime_context=_runtime_context(scope),
        )

    delta_events = [event for event in events if event.event in {"reasoning.delta", "message.delta"}]
    assert [(event.event, event.content) for event in delta_events] == [
        ("reasoning.delta", "先确认上下文。"),
        ("message.delta", "正文第一段，继续输出。"),
    ]
    assert completed_run.content == "正文第一段，继续输出。"
    assert completed_run.reasoning_content == "先确认上下文。"
    assert [item.content for item in snapshot.timeline_items if item.kind in {"reasoning", "message"}][-2:] == [
        "先确认上下文。",
        "正文第一段，继续输出。",
    ]


async def test_pydantic_event_projector_should_buffer_member_delta_chunks() -> None:
    """成员事件使用共享投影器时，连续小 chunk 应合并为较少的 member.message.delta。"""

    events = await _project_member_events(
        [
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="资源")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="整理")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="完成。")),
        ],
        flush=True,
    )

    assert [(event.event, event.content) for event in events] == [
        ("member.message.delta", "资源整理完成。"),
    ]
    assert events[0].data == {
        "member_run_id": "member-run-1",
        "member_agent_id": "resource-manager",
        "member_agent_name": "资源助手",
        "delegate_tool_call_id": "delegate-call-1",
    }


async def test_pydantic_event_projector_should_flush_member_text_before_tool_start() -> None:
    """成员工具事件开始前应先写出已缓冲文本，并保留成员 tool_call_id 映射。"""

    events = await _project_member_events(
        [
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="先检查现有资源。")),
            FunctionToolCallEvent(
                ToolCallPart(
                    tool_name="list_workspace_render_assets",
                    args={"workspace_id": 11},
                    tool_call_id="tool-list-assets",
                )
            ),
        ],
        flush=False,
    )

    assert [(event.event, event.content) for event in events] == [
        ("member.message.delta", "先检查现有资源。"),
        ("member.tool.started", None),
    ]
    assert events[1].data == {
        "member_run_id": "member-run-1",
        "member_agent_id": "resource-manager",
        "member_agent_name": "资源助手",
        "delegate_tool_call_id": "delegate-call-1",
        "tool_name": "list_workspace_render_assets",
        "tool_call_id": "member-run-1:tool-list-assets",
        "tool_args": {"workspace_id": 11},
        "raw_tool_call_id": "tool-list-assets",
    }


async def test_pydantic_event_projector_should_ignore_tool_part_start_until_function_call() -> None:
    """模型响应里的工具片段开始不等于工具执行，不能提前创建 running 工具。"""

    events = await _project_member_events(
        [
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="准备读取资源。")),
            PartStartEvent(
                index=1,
                part=ToolCallPart(
                    tool_name="list_workspace_render_assets",
                    args="",
                    tool_call_id="tool-list-assets",
                ),
            ),
        ],
        flush=True,
    )

    assert [(event.event, event.content) for event in events] == [
        ("member.message.delta", "准备读取资源。"),
    ]


async def test_pydantic_runner_should_flush_buffer_before_requested_cancel(
    authenticated_client: AsyncClient,
) -> None:
    """外部停止请求到达后，runner 应先写出已缓冲 delta，再写 run.cancelled。"""

    raw_delta_buffered = asyncio.Event()
    release_model = asyncio.Event()

    async def stream_function(
        messages: list[Any],
        info: AgentInfo,
    ) -> AsyncIterator[str]:
        """模拟模型先输出一段内容，然后等待测试触发取消。"""

        _ = messages, info
        yield "已流出的局部内容。"
        raw_delta_buffered.set()
        await release_model.wait()
        yield "这段不应写入。"

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner 取消 flush 工作空间",
        session_name="Pydantic Runner 取消 flush 会话",
    )
    model = FunctionModel(stream_function=stream_function)

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-cancel-flush",
            message="开始长任务",
            image_attachment_ids=[],
        )
        collect_task = asyncio.create_task(
            _collect_runner_events(
                PydanticAgentRunner(store).stream_run(
                    run_model=run_start.run_model,
                    agent_id="component-manager",
                    model=model,
                    model_settings={},
                    runtime_context=_runtime_context(scope),
                    message="开始长任务",
                )
            )
        )
        await asyncio.wait_for(raw_delta_buffered.wait(), timeout=3)
        async with get_session_factory()() as cancel_session:
            cancel_store = PlatformAgentRuntimeStore(cancel_session, user_id=1)
            await cancel_store.request_cancel(session_id=session_id, agent_id="component-manager")
        release_model.set()
        events = await asyncio.wait_for(collect_task, timeout=3)
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert completed_run is not None
        event_rows = (
            await db_session.execute(
                select(AiAgentRunEvent.event, AiAgentRunEvent.payload_json)
                .where(AiAgentRunEvent.run_id == run_start.run_model.run_id)
                .order_by(AiAgentRunEvent.event_index.asc())
            )
        ).all()

    assert [event.event for event in events] == ["model.request.started", "message.delta", "run.cancelled"]
    assert completed_run.status == "cancelled"
    assert completed_run.content == "已流出的局部内容。"
    assert [row[0] for row in event_rows] == [
        "run.started",
        "model.request.started",
        "run.cancelling",
        "message.delta",
        "run.cancelled",
    ]
    assert event_rows[3][1]["content"] == "已流出的局部内容。"


async def test_pydantic_runner_should_fail_idle_model_stream(
    authenticated_client: AsyncClient,
) -> None:
    """模型流长时间没有新事件时，应收敛为失败并写出已缓冲内容。"""

    async def stream_function(messages: list[Any], info: AgentInfo) -> AsyncIterator[str]:
        """模拟模型输出一段内容后半开卡住。"""

        _ = messages, info
        yield "已生成但未闭合的内容。"
        await asyncio.Event().wait()

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner 空闲超时工作空间",
        session_name="Pydantic Runner 空闲超时会话",
    )
    model = FunctionModel(stream_function=stream_function)

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-idle-timeout",
            message="开始长任务",
            image_attachment_ids=[],
        )
        events = await asyncio.wait_for(
            _collect_runner_events(
                PydanticAgentRunner(store, stream_idle_timeout_seconds=0.05).stream_run(
                    run_model=run_start.run_model,
                    agent_id="component-manager",
                    model=model,
                    model_settings={},
                    runtime_context=_runtime_context(scope),
                    message="开始长任务",
                )
            ),
            timeout=3,
        )
        failed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")

    assert failed_run is not None
    assert [event.event for event in events] == ["model.request.started", "message.delta", "run.error"]
    assert failed_run.status == "failed"
    assert failed_run.content == "已生成但未闭合的内容。"
    assert failed_run.error_code == "AI_AGENT_STREAM_IDLE_TIMEOUT"


async def test_pydantic_runner_should_emit_context_status_after_each_model_response(
    authenticated_client: AsyncClient,
) -> None:
    """同一 run 内多次 LLM 调用后，应逐次保存真实 usage 并推送 context.status。"""

    async def stream_function(messages: list[Any], info: AgentInfo) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """首次调用请求工具，收到工具结果后输出最终答案。"""

        _ = info
        if _latest_tool_return(messages) is not None:
            yield "已完成整理。"
            return
        yield {
            0: DeltaToolCall(
                name="context_probe",
                json_args='{"value":"alpha"}',
                tool_call_id="tool-context-probe",
            )
        }

    async def context_probe(value: str) -> str:
        """测试用普通工具，用于触发同一 run 内第二次模型调用。"""

        return f"工具结果：{value}"

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner context usage 工作空间",
        session_name="Pydantic Runner context usage 会话",
    )
    model = FunctionModel(stream_function=stream_function)
    budget = build_history_budget(
        SimpleNamespace(context_window_tokens=1200, max_output_tokens=100, compression_target_ratio=0.1),
        runtime_context=_runtime_context(scope),
    )

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="component-manager",
            scope=scope,
            run_id="pydantic-runner-context-usage",
            message="调用工具后继续。",
            image_attachment_ids=[],
        )
        events = await _collect_runner_events(
            PydanticAgentRunner(store).stream_run(
                run_model=run_start.run_model,
                agent_id="component-manager",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="调用工具后继续。",
                tools=[Tool(context_probe, name="context_probe")],
                context_budget=budget,
            )
        )
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="component-manager")
        assert completed_run is not None

    context_events = [event for event in events if event.event == "context.status"]
    response_messages = [
        item for item in completed_run.message_history_json
        if isinstance(item, dict) and item.get("kind") == "response"
    ]

    assert len(context_events) == 2
    assert all(event.data["context_used_tokens"] > 0 for event in context_events)
    assert context_events[-1].data["last_input_tokens"] > 0
    assert context_events[-1].data["last_output_tokens"] > 0
    assert len(response_messages) == 2
    assert completed_run.status == "completed"


def test_deferred_ask_user_should_accept_dict_and_json_args() -> None:
    """ask_user deferred 请求应同时兼容 Pydantic AI 传入的 dict 和 JSON 字符串参数。"""

    dict_requirement = _requirement_from_deferred(
        DeferredToolRequests(
            approvals=[
                ToolCallPart(
                    tool_name="ask_user",
                    args={
                        "questions": [
                            {
                                "question": "优先调整哪个区域？",
                                "options": [{"label": "首屏"}],
                            }
                        ]
                    },
                    tool_call_id="tool-dict",
                )
            ],
        ),
        run_id="run-dict",
        session_id="session-dict",
    )
    json_requirement = _requirement_from_deferred(
        DeferredToolRequests(
            approvals=[
                ToolCallPart(
                    tool_name="ask_user",
                    args='{"questions":[{"question":"优先调整哪个区域？","options":[{"label":"首屏"}]}]}',
                    tool_call_id="tool-json",
                )
            ],
        ),
        run_id="run-json",
        session_id="session-json",
    )

    assert dict_requirement.user_feedback_schema[0]["question"] == "优先调整哪个区域？"
    assert json_requirement.user_feedback_schema[0]["question"] == "优先调整哪个区域？"


def test_deferred_ask_user_should_reject_title_and_value_only_payload() -> None:
    """模型只输出 title/value 而没有 question 时，应明确失败。"""

    with pytest.raises(AppException) as exc_info:
        _requirement_from_deferred(
            DeferredToolRequests(
                approvals=[
                    ToolCallPart(
                        tool_name="ask_user",
                        args={
                            "questions": [
                                {
                                    "title": "目标区域",
                                    "value": "首屏",
                                    "options": [{"label": "首屏"}],
                                }
                            ]
                        },
                        tool_call_id="tool-bad",
                    )
                ],
            ),
            run_id="run-bad",
            session_id="session-bad",
        )

    assert exc_info.value.code == "AI_ASK_USER_SCHEMA_INVALID"


async def test_deferred_approval_tool_can_resume_with_call_result() -> None:
    """requires_approval 工具可通过 DeferredToolResults.calls 把外部结果直接返回给模型。"""

    model = FunctionModel(function=_ask_user_function, stream_function=_ask_user_stream_function)
    pydantic_agent = Agent(
        model,
        tools=[Tool(_ask_user_tool, name="ask_user", requires_approval=True)],
        output_type=[str, DeferredToolRequests],
    )
    first_result = await pydantic_agent.run("需要确认")
    assert isinstance(first_result.output, DeferredToolRequests)
    deferred_results = DeferredToolResults()
    deferred_results.calls["tool-ask-layout"] = (
        'User feedback received: [{"question": "页面应优先调整哪个区域？", "selected": ["首屏"]}]'
    )

    second_result = await pydantic_agent.run(
        "",
        message_history=ModelMessagesTypeAdapter.validate_python(
            ModelMessagesTypeAdapter.dump_python(first_result.all_messages(), mode="json")
        ),
        deferred_tool_results=deferred_results,
    )

    assert second_result.output == "我会优先调整首屏。"


async def _create_workspace_session(
    authenticated_client: AsyncClient,
    *,
    workspace_name: str,
    session_name: str,
    agent_id: str = "component-manager",
    source: str = "editor-component-library",
) -> tuple[int, str, AgentScopeContext]:
    """创建工作空间和指定智能体会话。"""

    workspace_id, scope = await _create_workspace_scope(
        authenticated_client,
        workspace_name=workspace_name,
        source=source,
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": agent_id,
            "session_name": session_name,
            "scope": scope.model_dump(mode="json"),
        },
    )
    assert session_response.status_code == 201
    return workspace_id, session_response.json()["session_id"], scope


async def _create_workspace_scope(
    authenticated_client: AsyncClient,
    *,
    workspace_name: str,
    source: str,
) -> tuple[int, AgentScopeContext]:
    """创建工作空间并返回测试用 scope。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": workspace_name, "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    return workspace_id, AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace_id,
        source=source,
    )


def _runtime_context(scope: AgentScopeContext) -> AgentRuntimeContext:
    """把测试 scope 转成 runner 需要的运行时上下文。"""

    return AgentRuntimeContext(
        scope_type=scope.scope_type,
        workspace_id=scope.workspace_id,
        project_id=scope.project_id,
        page_id=scope.page_id,
        component_id=scope.component_id,
        source=scope.source,
    )


async def _collect_runner_events(stream: AsyncIterator[bytes]) -> list[Any]:
    """消费 runner SSE，并返回其中的 AgentRunEvent。"""

    events = []
    async for _chunk in stream:
        # runner 写入事件后返回的是 SSE bytes；测试只需要数据库实体已经同步后的事件对象。
        text = _chunk.decode("utf-8")
        for block in text.strip().split("\n\n"):
            if not block.startswith("data:"):
                continue
            raw_payload = block.removeprefix("data:").strip()
            from app.schemas.agent import AgentRunEvent

            events.append(AgentRunEvent.model_validate_json(raw_payload))
    return events


async def _project_member_events(raw_events: list[Any], *, flush: bool) -> list[Any]:
    """用共享投影器把测试原始事件转换为 member.* 平台事件。"""

    stored_events: list[Any] = []

    async def append_event(event: Any) -> Any:
        """记录投影结果，模拟运行态 store append_event。"""

        stored_events.append(event)
        return event

    projector = PydanticEventProjector(
        run_id="parent-run-1",
        session_id="session-1",
        append_event=append_event,
        event_prefix="member.",
        base_event_data=lambda: {
            "member_run_id": "member-run-1",
            "member_agent_id": "resource-manager",
            "member_agent_name": "资源助手",
            "delegate_tool_call_id": "delegate-call-1",
        },
        map_tool_call_id=lambda raw_tool_call_id: f"member-run-1:{raw_tool_call_id}" if raw_tool_call_id else None,
        extra_tool_data=lambda raw_tool_call_id: {"raw_tool_call_id": raw_tool_call_id},
    )
    for raw_event in raw_events:
        await projector.handle_raw_event(raw_event)
    if flush:
        await projector.flush_delta_buffer()
    return stored_events


async def _ask_user_tool(questions: list[dict[str, Any]]) -> str:
    """测试用 ask_user 工具；实际返回不会被执行，继续时由 calls 注入。"""

    _ = questions
    return "工具不应实际执行。"


async def _approval_write_tool(value: str) -> str:
    """测试用高风险写入工具；实际返回不重要，确认前不会执行。"""

    return f"已写入：{value}"


@agent_tool(show_result=False)
async def recoverable_error_tool(run_context: AgentToolContext) -> dict[str, Any]:
    """测试用业务错误工具，模拟模型选择了不可读取内容的资源。"""

    _ = run_context
    raise AppException(status_code=400, code="ASSET_CONTENT_READ_UNSUPPORTED", detail="该资源不支持内容读取。")


class _FakeMemberDelegationExecutor:
    """测试用成员委派执行器，只记录入参并返回固定成员结果。"""

    def __init__(self) -> None:
        """初始化调用记录。"""

        self.calls: list[dict[str, Any]] = []

    async def delegate_task_to_member(
        self,
        *,
        member_id: str,
        task: str,
        handoff_context: str | None,
        expected_output: str | None,
        delegate_tool_call_id: str | None,
        delegate_tool_name: str,
    ) -> dict[str, Any]:
        """模拟单成员委派完成，并返回可供内容助手继续推理的结果。"""

        self.calls.append(
            {
                "member_id": member_id,
                "task": task,
                "handoff_context": handoff_context,
                "expected_output": expected_output,
                "delegate_tool_call_id": delegate_tool_call_id,
                "delegate_tool_name": delegate_tool_name,
            }
        )
        return {
            "member_run_id": "member-run-fake-resource",
            "member_id": member_id,
            "member_name": "资源助手",
            "status": "completed",
            "result": "已准备资源 hero_cover。",
        }


async def _ask_user_stream_function(
    messages: list[Any],
    info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall] | dict[int, DeltaThinkingPart]]:
    """模拟真实 LLM：先输出思考和提问，收到工具返回后输出最终答案。"""

    _ = info
    tool_return = _latest_tool_return(messages)
    if tool_return is not None:
        yield {0: DeltaThinkingPart(content="收到用户反馈。")}
        yield "我会优先调整首屏。"
        return
    yield {0: DeltaThinkingPart(content="先确认用户偏好。")}
    yield "我需要确认页面调整范围。"
    yield {
        1: DeltaToolCall(
            name="ask_user",
            json_args=(
                '{"questions":[{"question":"页面应优先调整哪个区域？",'
                '"options":[{"label":"首屏"},{"label":"全页面"}]}]}'
            ),
            tool_call_id="tool-ask-layout",
        )
    }


async def _approval_tool_stream_function(
    messages: list[Any],
    info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """模拟模型先请求确认写入工具，收到拒绝回灌后继续输出总结。"""

    _ = info
    if _latest_tool_return(messages) is not None:
        yield "已跳过写入。"
        return
    yield {
        0: DeltaToolCall(
            name="dangerous_write",
            json_args='{"value":"route-tree"}',
            tool_call_id="tool-write-route",
        )
    }


async def _recoverable_tool_error_stream_function(
    messages: list[Any],
    info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """模拟模型收到工具业务错误后改用其他方案继续完成。"""

    _ = info
    if _latest_tool_return(messages) is not None:
        yield "已换用其他资源继续。"
        return
    yield {
        0: DeltaToolCall(
            name="recoverable_error_tool",
            json_args="{}",
            tool_call_id="tool-recoverable-read",
        )
    }


async def _member_delegation_stream_function(
    messages: list[Any],
    info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
    """模拟内容助手先委派资源助手，收到成员结果后继续输出最终回复。"""

    _ = info
    if _latest_tool_return(messages) is not None:
        yield "已整合资源助手结果。"
        return
    yield {
        0: DeltaToolCall(
            name="delegate_task_to_member",
            json_args=(
                '{"member_id":"resource-manager","task":"整理封面图资源",'
                '"handoff_context":"页面需要封面视觉资源","expected_output":"返回可引用资源名"}'
            ),
            tool_call_id="tool-delegate-resource",
        )
    }


async def _ask_user_function(messages: list[Any], info: AgentInfo) -> ModelResponse:
    """测试用非流式模型函数，验证 Pydantic AI deferred calls 契约。"""

    _ = info
    if _latest_tool_return(messages) is not None:
        return ModelResponse(
            parts=[
                ThinkingPart(content="收到用户反馈。"),
                TextPart(content="我会优先调整首屏。"),
            ],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name="ask_user",
                args={
                    "questions": [
                        {
                            "question": "页面应优先调整哪个区域？",
                            "options": [{"label": "首屏"}, {"label": "全页面"}],
                        }
                    ]
                },
                tool_call_id="tool-ask-layout",
            )
        ],
        usage=RequestUsage(input_tokens=1, output_tokens=1),
    )


async def _bad_ask_user_stream_function(
    messages: list[Any],
    info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaToolCall] | dict[int, DeltaThinkingPart]]:
    """模拟模型输出旧式 title/value 参数。"""

    _ = messages, info
    yield "我需要确认一下。"
    yield {
        0: DeltaToolCall(
            name="ask_user",
            json_args='{"questions":[{"title":"目标区域","value":"首屏","options":[{"label":"首屏"}]}]}',
            tool_call_id="tool-bad-ask",
        )
    }


async def _chunked_delta_stream_function(
    messages: list[Any],
    info: AgentInfo,
) -> AsyncIterator[str | dict[int, DeltaThinkingPart]]:
    """模拟模型连续输出同类 thinking/text chunk。"""

    _ = messages, info
    yield {0: DeltaThinkingPart(content="先")}
    yield {0: DeltaThinkingPart(content="确认")}
    yield {0: DeltaThinkingPart(content="上下文。")}
    yield "正文第一段，"
    yield "继续输出。"


def _latest_tool_return(messages: list[Any]) -> Any | None:
    """从 Pydantic AI 历史消息中读取最近工具返回。"""

    for message in reversed(messages):
        for part in reversed(getattr(message, "parts", [])):
            if getattr(part, "part_kind", None) == "tool-return":
                return getattr(part, "content", None)
    return None
