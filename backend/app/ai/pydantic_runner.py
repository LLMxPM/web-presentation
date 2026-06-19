"""文件功能：把 Pydantic AI 执行过程转换为平台 AgentRunEvent 并写入运行态表。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from pydantic_ai import Agent, AgentRunResultEvent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessagesTypeAdapter,
    PartDeltaEvent,
    PartStartEvent,
    ThinkingPart,
    ThinkingPartDelta,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    UserContent,
)

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, build_effective_description, build_effective_instructions
from app.ai.platform_runtime import PlatformAgentRuntimeStore, encode_sse_event
from app.ai.pydantic_tools import AgentToolDeps
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun
from app.schemas.agent import AgentPendingRequirement, AgentRunEvent


class PydanticAgentRunner:
    """执行 Pydantic AI Agent，并将内部事件投影为平台事件。"""

    def __init__(self, store: PlatformAgentRuntimeStore) -> None:
        """保存运行态 store。"""

        self._store = store

    async def stream_run(
        self,
        *,
        run_model: AiAgentRun,
        agent_id: str,
        model: Any,
        model_settings: dict[str, Any],
        runtime_context: AgentRuntimeContext,
        message: str | list[UserContent],
        agent_config: EffectiveAgentRuntimeConfig | None = None,
        tools: list[Any] | None = None,
        deps: AgentToolDeps | None = None,
        message_history: list[Any] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """执行一次 Pydantic AI run 并输出平台 SSE。"""

        catalog = get_agent_catalog_entry(agent_id)
        if catalog is None:
            raise RuntimeError(f"agent catalog is not initialized: {agent_id}")
        instructions = [
            *build_effective_instructions(catalog, agent_config),
            build_scope_context_text(runtime_context),
        ]
        agent = Agent(
            model,
            name=agent_id,
            output_type=[str, DeferredToolRequests],
            instructions=instructions,
            system_prompt=build_effective_description(catalog, agent_config),
            deps_type=AgentToolDeps if deps is not None else type(None),
            tools=tools or (),
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        final_messages: list[dict[str, Any]] = []
        try:
            yield await self._yield_and_store(
                run_model,
                AgentRunEvent(event="model.request.started", run_id=run_model.run_id, session_id=run_model.session_id),
            )
            async for raw_event in agent.run_stream_events(
                message if message else None,
                model_settings=model_settings or None,
                deps=deps,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                infer_name=False,
            ):
                should_stop, cancel_event = await self._cancel_event_if_requested(run_model)
                if should_stop:
                    if cancel_event is None:
                        return
                    yield cancel_event
                    return
                async for sse in self._handle_raw_event(
                    run_model=run_model,
                    raw_event=raw_event,
                    content_parts=content_parts,
                    reasoning_parts=reasoning_parts,
                    final_messages=final_messages,
                ):
                    yield sse
            if _has_paused(run_model):
                await self._store.save_run_message_history(run_model, final_messages)
                return
            should_stop, cancel_event = await self._cancel_event_if_requested(run_model)
            if should_stop:
                if cancel_event is None:
                    return
                yield cancel_event
                return
            yield await self._yield_and_store(
                run_model,
                AgentRunEvent(event="model.request.completed", run_id=run_model.run_id, session_id=run_model.session_id),
            )
            await self._store.append_assistant_message(
                run_model,
                content="".join(content_parts),
                reasoning_content="".join(reasoning_parts) or None,
                message_history=final_messages,
            )
            event = await self._store.mark_terminal(run_model, status="completed", content="".join(content_parts) or None)
            yield encode_sse_event(event)
        except AppException as exc:
            if exc.code == "AI_RUN_CANCELLED":
                event = await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
                yield encode_sse_event(event)
                return
            event = await self._store.mark_terminal(
                run_model,
                status="failed",
                error_code=exc.code,
                error_message=exc.detail,
            )
            yield encode_sse_event(event)
        except Exception as exc:  # noqa: BLE001
            event = await self._store.mark_terminal(
                run_model,
                status="failed",
                error_code="AI_RUN_FAILED",
                error_message=str(exc) or "智能体执行失败，请稍后重试。",
            )
            yield encode_sse_event(event)

    async def _handle_raw_event(
        self,
        *,
        run_model: AiAgentRun,
        raw_event: Any,
        content_parts: list[str],
        reasoning_parts: list[str],
        final_messages: list[dict[str, Any]],
    ) -> AsyncGenerator[bytes, None]:
        """把单个 Pydantic AI 事件转换为零到多个平台 SSE。"""

        if isinstance(raw_event, AgentRunResultEvent):
            output = getattr(raw_event.result, "output", None)
            if isinstance(output, DeferredToolRequests):
                requirement = _requirement_from_deferred(
                    output,
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                )
                event = await self._store.pause_for_requirement(run_model, requirement=requirement)
                yield encode_sse_event(event)
            final_messages[:] = _safe_messages(raw_event.result)
            return
        if isinstance(raw_event, PartStartEvent):
            part = raw_event.part
            if isinstance(part, TextPart) and part.content:
                content_parts.append(part.content)
                yield await self._yield_and_store(
                    run_model,
                    AgentRunEvent(
                        event="message.delta",
                        run_id=run_model.run_id,
                        session_id=run_model.session_id,
                        content=part.content,
                    ),
                )
            elif isinstance(part, ThinkingPart) and part.content:
                reasoning_parts.append(part.content)
                yield await self._yield_and_store(
                    run_model,
                    AgentRunEvent(
                        event="reasoning.delta",
                        run_id=run_model.run_id,
                        session_id=run_model.session_id,
                        content=part.content,
                    ),
                )
            elif isinstance(part, ToolCallPart):
                yield await self._yield_and_store(
                    run_model,
                    AgentRunEvent(
                        event="tool.started",
                        run_id=run_model.run_id,
                        session_id=run_model.session_id,
                        data=_tool_payload(part),
                    ),
                )
        elif isinstance(raw_event, PartDeltaEvent):
            delta = raw_event.delta
            if isinstance(delta, TextPartDelta) and delta.content_delta:
                content_parts.append(delta.content_delta)
                yield await self._yield_and_store(
                    run_model,
                    AgentRunEvent(
                        event="message.delta",
                        run_id=run_model.run_id,
                        session_id=run_model.session_id,
                        content=delta.content_delta,
                    ),
                )
            elif isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                reasoning_parts.append(delta.content_delta)
                yield await self._yield_and_store(
                    run_model,
                    AgentRunEvent(
                        event="reasoning.delta",
                        run_id=run_model.run_id,
                        session_id=run_model.session_id,
                        content=delta.content_delta,
                    ),
                )
        elif isinstance(raw_event, FunctionToolCallEvent):
            yield await self._yield_and_store(
                run_model,
                AgentRunEvent(
                    event="tool.started",
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                    data=_tool_payload(raw_event.part),
                ),
            )
        elif isinstance(raw_event, FunctionToolResultEvent):
            result = raw_event.result
            yield await self._yield_and_store(
                run_model,
                AgentRunEvent(
                    event="tool.completed",
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                    data={
                        "tool_name": getattr(result, "tool_name", None),
                        "tool_call_id": getattr(result, "tool_call_id", None),
                        "result": getattr(result, "content", None),
                    },
                ),
            )

    async def _yield_and_store(self, run_model: AiAgentRun, event: AgentRunEvent) -> bytes:
        """写入事件表并返回 SSE bytes。"""

        stored = await self._store.append_event(run_model, event)
        return encode_sse_event(stored)

    async def _cancel_event_if_requested(self, run_model: AiAgentRun) -> tuple[bool, bytes | None]:
        """如果外部已结束或请求取消，则返回是否应停止当前 runner 以及可选 SSE。"""

        status = await self._store.refresh_run_control_state(run_model)
        if status in {"completed", "cancelled", "failed"}:
            return True, None
        if status == "cancelling" or run_model.cancel_requested_at is not None:
            event = await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
            return True, encode_sse_event(event)
        return False, None


def _tool_payload(part: ToolCallPart) -> dict[str, Any]:
    """把 Pydantic AI 工具调用片段转换为平台工具 payload。"""

    return {
        "tool_name": part.tool_name,
        "tool_call_id": part.tool_call_id,
        "tool_args": part.args,
    }


def _safe_messages(result: Any) -> list[dict[str, Any]]:
    """安全序列化 Pydantic AI result 历史消息。"""

    try:
        dumped = ModelMessagesTypeAdapter.dump_python(result.all_messages(), mode="json")
        return dumped if isinstance(dumped, list) else []
    except Exception:  # noqa: BLE001
        return []


def _requirement_from_deferred(
    requests: DeferredToolRequests,
    *,
    run_id: str,
    session_id: str,
) -> AgentPendingRequirement:
    """把 Pydantic AI deferred requests 转换为平台 pending requirement。"""

    call = (requests.approvals or requests.calls)[0] if (requests.approvals or requests.calls) else None
    tool_name = getattr(call, "tool_name", None) if call is not None else None
    tool_call_id = getattr(call, "tool_call_id", None) if call is not None else None
    args = _tool_args_as_dict(getattr(call, "args", None) if call is not None else None)
    feedback_schema = _feedback_schema_from_args(args) if tool_name == "ask_user" else []
    kind = "user_feedback" if tool_name == "ask_user" else "confirmation"
    if kind == "user_feedback" and not feedback_schema:
        raise AppException(
            status_code=422,
            code="AI_ASK_USER_SCHEMA_INVALID",
            detail="ask_user 工具调用缺少可展示的问题，请使用 questions[].question 提供问题文案。",
        )
    return AgentPendingRequirement(
        id=f"requirement-{tool_call_id or run_id}",
        kind=kind,
        run_id=run_id,
        session_id=session_id,
        tool_name=tool_name,
        tool_execution={
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_args": args,
            **({"requires_user_input": True, "user_feedback_schema": feedback_schema} if feedback_schema else {}),
            "deferred_metadata": requests.metadata,
        },
        user_feedback_schema=feedback_schema,
        note="需要用户回答后继续。" if kind == "user_feedback" else f"工具 {tool_name or 'unknown'} 需要确认后执行。",
    )


def _has_paused(run_model: AiAgentRun) -> bool:
    """判断当前 run 是否已进入暂停状态。"""

    return run_model.status == "paused"


def _tool_args_as_dict(value: Any) -> dict[str, Any]:
    """把 Pydantic AI 工具参数归一化为 dict，兼容字符串 JSON。"""

    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _feedback_schema_from_args(args: dict[str, Any]) -> list[dict[str, Any]]:
    """从 ask_user 参数中提取前端可渲染的结构化问题。"""

    questions = args.get("questions")
    if not isinstance(questions, list):
        return []
    result: list[dict[str, Any]] = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        normalized = dict(item)
        normalized["question"] = question
        normalized["multi_select"] = False
        options = normalized.get("options")
        normalized["options"] = options if isinstance(options, list) else []
        result.append(normalized)
    return result
