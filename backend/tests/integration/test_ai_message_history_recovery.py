"""文件功能：验证异常 Run 可从平台消息、事件和工具账本恢复安全模型历史。"""

from __future__ import annotations

import json

from httpx import AsyncClient
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from sqlalchemy import select

from app.ai.message_history import rebuild_agent_message_history
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRun, AiAgentToolCall
from app.schemas.agent import AgentRunEvent, AgentScopeContext


async def test_failed_first_response_should_restore_user_input_and_visible_draft(
    authenticated_client: AsyncClient,
) -> None:
    """首次响应超时后应补回用户输入和可见草稿，但不得注入 reasoning。"""

    session_id, scope = await _create_session(authenticated_client, "首次响应中断")
    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        started = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id="history-recovery-first-response",
            message="请分析这张页面",
            image_attachment_ids=[],
        )
        await store.append_event(started.run_model, AgentRunEvent(event="message.delta", content="我先检查页面结构。"))
        await store.append_event(started.run_model, AgentRunEvent(event="reasoning.delta", content="隐藏推理不得恢复"))
        await store.mark_terminal(
            started.run_model,
            status="failed",
            error_code="AI_AGENT_STREAM_IDLE_TIMEOUT",
            error_message="模型流超时。",
        )

        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="agent-coordinator",
        )
        snapshot = await store.get_runtime_snapshot(
            session_id=session_id,
            agent_id="agent-coordinator",
            runtime_context=None,
        )

    serialized = json.dumps(rebuilt.message_json, ensure_ascii=False)
    assert "请分析这张页面" in serialized
    assert "我先检查页面结构。" in serialized
    assert "非权威未完成草稿" not in serialized
    assert "仅供参考，不代表最终结论" in serialized
    assert "隐藏推理不得恢复" not in serialized
    assert rebuilt.recovery_by_run[started.run_model.run_id]["user_input_restored"] is True
    assistant_item = next(item for item in snapshot.timeline_items if item.kind == "message" and item.role == "assistant")
    assert assistant_item.status == "interrupted"


async def test_completed_tool_should_close_raw_open_call_without_duplicate(
    authenticated_client: AsyncClient,
) -> None:
    """工具已完成但后续模型超时时，应从账本补回一次工具返回并保留原检查点。"""

    session_id, scope = await _create_session(authenticated_client, "工具完成后中断")
    raw_history = _tool_call_history("读取页面", "get_page_content", "tool-read-page")
    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        started = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id="history-recovery-completed-tool",
            message="读取页面",
            image_attachment_ids=[],
        )
        await store.save_run_message_history(started.run_model, raw_history)
        await store.append_event(started.run_model, AgentRunEvent(
            event="tool.started",
            data={"tool_name": "get_page_content", "tool_call_id": "tool-read-page", "tool_args": {"page_id": 12}},
        ))
        await store.append_event(started.run_model, AgentRunEvent(
            event="tool.completed",
            data={"tool_name": "get_page_content", "tool_call_id": "tool-read-page", "result": {"content": "页面源码"}},
        ))
        await store.mark_terminal(started.run_model, status="failed", error_code="AI_RUN_FAILED", error_message="总结失败。")
        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="agent-coordinator",
        )
        persisted = await db_session.get(AiAgentRun, started.run_model.run_id)

    serialized = json.dumps(rebuilt.message_json, ensure_ascii=False)
    assert persisted is not None and persisted.message_history_json == raw_history
    assert serialized.count('"tool_call_id": "tool-read-page"') == 2
    assert "页面源码" in serialized
    assert rebuilt.recovery_by_run[started.run_model.run_id]["restored_tool_call_ids"] == ["tool-read-page"]


async def test_unknown_tool_outcome_should_not_create_tool_return(
    authenticated_client: AsyncClient,
) -> None:
    """运行中的工具随 Run 中断时只能记录结果未知，不得构造虚假工具返回。"""

    session_id, scope = await _create_session(authenticated_client, "工具结果未知")
    raw_history = _tool_call_history("更新页面", "update_page_source", "tool-update-page")
    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        started = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id="history-recovery-unknown-tool",
            message="更新页面",
            image_attachment_ids=[],
        )
        await store.save_run_message_history(started.run_model, raw_history)
        await store.append_event(started.run_model, AgentRunEvent(
            event="tool.started",
            data={"tool_name": "update_page_source", "tool_call_id": "tool-update-page", "tool_args": {"page_id": 18}},
        ))
        await store.mark_terminal(started.run_model, status="failed", error_code="AI_RUN_FAILED", error_message="连接中断。")
        rebuilt = await rebuild_agent_message_history(
            session=db_session,
            user_id=1,
            session_id=session_id,
            agent_id="agent-coordinator",
        )
        tool = await db_session.scalar(select(AiAgentToolCall).where(AiAgentToolCall.tool_call_id == "tool-update-page"))

    serialized = json.dumps(rebuilt.message_json, ensure_ascii=False)
    assert tool is not None and tool.status == "interrupted"
    assert "执行结果未知" in serialized
    assert "必须先查询目标实体当前状态" in serialized
    assert '"part_kind": "tool-return"' not in serialized
    assert rebuilt.recovery_by_run[started.run_model.run_id]["trimmed_tool_call_ids"] == ["tool-update-page"]


async def _create_session(authenticated_client: AsyncClient, suffix: str) -> tuple[str, AgentScopeContext]:
    """创建恢复集成测试所需工作空间、模型配置和智能体会话。"""

    workspace = await authenticated_client.post("/api/workspaces", json={"name": f"历史恢复-{suffix}", "status": "active"})
    assert workspace.status_code == 200
    provider = await authenticated_client.post("/api/ai/llm-provider-configs", json={
        "name": f"历史恢复供应商-{suffix}",
        "provider_key": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-history-recovery-test",
    })
    assert provider.status_code == 201
    model = await authenticated_client.post("/api/ai/llm-configs", json={
        "name": f"历史恢复模型-{suffix}",
        "provider_config_id": provider.json()["id"],
        "model_id": "gpt-4.1-mini",
        "advanced_config_json": {},
    })
    assert model.status_code == 201
    session = await authenticated_client.post("/api/ai/sessions", json={
        "agent_id": "agent-coordinator",
        "session_name": suffix,
        "workspace_id": workspace.json()["id"],
        "llm_config_id": model.json()["id"],
    })
    assert session.status_code == 201
    return session.json()["session_id"], AgentScopeContext(
        scope_type="workspace",
        workspace_id=workspace.json()["id"],
        source="history-recovery-test",
    )


def _tool_call_history(user_text: str, tool_name: str, tool_call_id: str) -> list[dict[str, object]]:
    """构造含可见文本与未闭合工具调用的原始检查点。"""

    dumped = ModelMessagesTypeAdapter.dump_python([
        ModelRequest(parts=[UserPromptPart(content=user_text)]),
        ModelResponse(parts=[
            TextPart(content="我先执行工具。"),
            ToolCallPart(tool_name=tool_name, args={}, tool_call_id=tool_call_id),
        ]),
    ], mode="json")
    assert isinstance(dumped, list)
    return dumped
