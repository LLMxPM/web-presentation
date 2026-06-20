"""文件功能：把 Pydantic AI 执行过程转换为平台 AgentRunEvent 并写入运行态表。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Sequence
from contextlib import suppress
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import UserContent

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, build_effective_description, build_effective_instructions
from app.ai.member_delegation import MemberDelegationPaused
from app.ai.platform_runtime import PlatformAgentRuntimeStore, encode_sse_event, stream_live_subscribe, subscribe_live_run_events
from app.ai.pydantic_event_projection import PydanticEventProjector, safe_messages
from app.ai.pydantic_tools import AgentToolDeps
from app.ai.run_errors import normalize_agent_run_exception
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun
from app.schemas.agent import AgentPendingRequirement, AgentRunEvent

logger = logging.getLogger(__name__)


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
        history_processors: Sequence[Any] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """执行一次 Pydantic AI run 并输出平台 SSE。"""

        live_queue = subscribe_live_run_events(run_id=run_model.run_id)
        task = asyncio.create_task(
            self._drain_stream_run_direct(
                run_model=run_model,
                agent_id=agent_id,
                model=model,
                model_settings=model_settings,
                runtime_context=runtime_context,
                message=message,
                agent_config=agent_config,
                tools=tools,
                deps=deps,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                history_processors=history_processors,
            )
        )
        try:
            async for chunk in stream_live_subscribe(run_id=run_model.run_id, queue=live_queue):
                yield chunk
            await task
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _drain_stream_run_direct(
        self,
        **kwargs: Any,
    ) -> None:
        """消费内部直接事件流；当前响应统一通过事件表订阅输出。"""

        async for _ in self._stream_run_direct(**kwargs):
            pass

    async def run_to_store(self, **kwargs: Any) -> None:
        """仅执行 run 并写入事件表，调用方自行负责 SSE 回放。"""

        await self._drain_stream_run_direct(**kwargs)

    async def _stream_run_direct(
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
        history_processors: Sequence[Any] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """执行 Pydantic AI run 并写入平台事件；直接产物仅供内部消费。"""

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        final_messages: list[dict[str, Any]] = []
        projector: PydanticEventProjector | None = None
        try:
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
                history_processors=history_processors,
            )
            projector = PydanticEventProjector(
                run_id=run_model.run_id,
                session_id=run_model.session_id,
                append_event=lambda event: self._store.append_event(run_model, event),
                deferred_tool_results=deferred_tool_results,
                final_messages=final_messages,
                on_message_delta=content_parts.append,
                on_reasoning_delta=reasoning_parts.append,
                on_deferred=lambda requests, _messages: self._pause_for_deferred_tools(run_model, requests),
            )
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
                should_stop, should_cancel = await self._cancel_event_if_requested(run_model)
                if should_stop:
                    async for sse in self._flush_projector_buffer(projector, best_effort=True):
                        yield sse
                    if not should_cancel:
                        return
                    event = await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
                    yield encode_sse_event(event)
                    return
                for event in await projector.handle_raw_event(raw_event):
                    yield encode_sse_event(event)
            if _has_paused(run_model):
                async for sse in self._flush_projector_buffer(projector):
                    yield sse
                await self._store.save_run_message_history(run_model, final_messages)
                return
            should_stop, should_cancel = await self._cancel_event_if_requested(run_model)
            if should_stop:
                async for sse in self._flush_projector_buffer(projector, best_effort=True):
                    yield sse
                if not should_cancel:
                    return
                event = await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
                yield encode_sse_event(event)
                return
            async for sse in self._flush_projector_buffer(projector):
                yield sse
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
        except MemberDelegationPaused as exc:
            async for sse in self._flush_projector_buffer(projector, best_effort=True):
                yield sse
            await self._store.save_run_message_history(run_model, final_messages)
            event = await self._store.pause_for_requirement(run_model, requirement=exc.requirement)
            yield encode_sse_event(event)
        except AppException as exc:
            async for sse in self._flush_projector_buffer(projector, best_effort=True):
                yield sse
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
            async for sse in self._flush_projector_buffer(projector, best_effort=True):
                yield sse
            failure = normalize_agent_run_exception(
                exc,
                fallback_code="AI_RUN_FAILED",
            )
            logger.exception(
                "Agent run failed while streaming model events",
                extra={
                    "run_id": run_model.run_id,
                    "session_id": run_model.session_id,
                    "agent_id": agent_id,
                    "error_code": failure.code,
                    "raw_error_message": failure.raw_message,
                },
            )
            event = await self._store.mark_terminal(
                run_model,
                status="failed",
                error_code=failure.code,
                error_message=failure.message,
            )
            yield encode_sse_event(event)

    async def _pause_for_deferred_tools(
        self,
        run_model: AiAgentRun,
        requests: DeferredToolRequests,
    ) -> AgentRunEvent:
        """把 Pydantic AI deferred 请求转换为平台暂停事件。"""

        return await self._store.pause_for_requirement(
            run_model,
            requirement=_requirement_from_deferred(
                requests,
                run_id=run_model.run_id,
                session_id=run_model.session_id,
            ),
        )

    async def _flush_projector_buffer(
        self,
        projector: PydanticEventProjector | None,
        *,
        best_effort: bool = False,
    ) -> AsyncGenerator[bytes, None]:
        """写出共享投影器里的 delta 缓冲并转换为 SSE bytes。"""

        if projector is None:
            return
        for event in await projector.flush_delta_buffer(best_effort=best_effort):
            yield encode_sse_event(event)

    async def _yield_and_store(self, run_model: AiAgentRun, event: AgentRunEvent) -> bytes:
        """写入事件表并返回 SSE bytes。"""

        stored = await self._store.append_event(run_model, event)
        return encode_sse_event(stored)

    async def _cancel_event_if_requested(self, run_model: AiAgentRun) -> tuple[bool, bool]:
        """如果外部已结束或请求取消，则返回是否停止以及是否需要写取消终态。"""

        status = await self._store.refresh_run_control_state(run_model)
        if status in {"completed", "cancelled", "failed"}:
            return True, False
        if status == "cancelling" or run_model.cancel_requested_at is not None:
            return True, True
        return False, False

def _safe_messages(result: Any) -> list[dict[str, Any]]:
    """安全序列化 Pydantic AI result 历史消息。"""

    return safe_messages(result)


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
