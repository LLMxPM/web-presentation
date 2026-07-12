"""文件功能：把 Pydantic AI 执行过程转换为平台 AgentRunEvent 并写入运行态表。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Sequence
from time import monotonic
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import ModelMessagesTypeAdapter, UserContent

from app.ai.agent.runtime_context import AgentRuntimeContext, build_scope_context_text
from app.ai.agent_catalog import get_agent_catalog_entry
from app.ai.agent_runtime_config import EffectiveAgentRuntimeConfig, build_effective_instructions
from app.ai.history_compression import HistoryCompressionService
from app.ai.message_history import AgentContextLimitProcessor, AgentHistoryBudget, build_context_status_item
from app.ai.member_delegation import MemberDelegationPaused
from app.ai.platform_runtime import (
    PlatformAgentRuntimeStore,
    encode_sse_event,
    get_live_run_activity_version,
    stream_live_subscribe,
    subscribe_live_run_events,
)
from app.ai.pydantic_event_projection import PydanticEventProjector, safe_messages, safe_new_messages
from app.ai.pydantic_tools import AgentToolDeps
from app.ai.run_errors import build_agent_error_log_extra, normalize_agent_run_exception
from app.core.exceptions import AppException
from app.core.config import get_settings
from app.models.ai_agent_runtime import AiAgentRun
from app.schemas.agent import AgentPendingRequirement, AgentRunEvent

logger = logging.getLogger(__name__)

_STREAM_CONTROL_POLL_INTERVAL_SECONDS = 0.5
_STREAM_TASK_CANCEL_GRACE_SECONDS = 1.0


class PydanticAgentRunner:
    """执行 Pydantic AI Agent，并将内部事件投影为平台事件。"""

    def __init__(
        self,
        store: PlatformAgentRuntimeStore,
        *,
        stream_idle_timeout_seconds: float | None = None,
        tool_stream_idle_timeout_seconds: float | None = None,
        stream_cancel_grace_seconds: float | None = None,
    ) -> None:
        """保存运行态 store，并分别解析模型流与工具流空闲超时。"""

        self._store = store
        self._stream_idle_timeout_seconds = (
            float(stream_idle_timeout_seconds)
            if stream_idle_timeout_seconds is not None
            else float(get_settings().ai_agent_stream_idle_timeout_seconds)
        )
        self._tool_stream_idle_timeout_seconds = (
            float(tool_stream_idle_timeout_seconds)
            if tool_stream_idle_timeout_seconds is not None
            else float(get_settings().ai_agent_tool_stream_idle_timeout_seconds)
        )
        self._stream_cancel_grace_seconds = (
            max(0.01, float(stream_cancel_grace_seconds))
            if stream_cancel_grace_seconds is not None
            else _STREAM_TASK_CANCEL_GRACE_SECONDS
        )

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
        context_budget: AgentHistoryBudget | None = None,
        context_processor: AgentContextLimitProcessor | None = None,
        message_image_refs: list[dict[str, Any]] | None = None,
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
                context_budget=context_budget,
                context_processor=context_processor,
                message_image_refs=message_image_refs,
            )
        )
        try:
            async for chunk in stream_live_subscribe(run_id=run_model.run_id, queue=live_queue):
                yield chunk
            await task
        except asyncio.CancelledError:
            await self._cancel_pending_stream_task(task)
            raise
        finally:
            if not task.done():
                await self._cancel_pending_stream_task(task)

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
        context_budget: AgentHistoryBudget | None = None,
        context_processor: AgentContextLimitProcessor | None = None,
        message_image_refs: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """执行 Pydantic AI run 并写入平台事件；直接产物仅供内部消费。"""

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        final_messages: list[dict[str, Any]] = []
        base_run_message_history = _message_dicts(
            run_model.message_history_json if isinstance(run_model.message_history_json, list) else []
        )
        previous_message_history_count = max(0, len(message_history or []) - len(base_run_message_history))
        projector: PydanticEventProjector | None = None
        try:
            catalog = get_agent_catalog_entry(agent_id)
            if catalog is None:
                raise RuntimeError(f"agent catalog is not initialized: {agent_id}")
            instructions = build_effective_instructions(
                catalog,
                agent_config,
                build_scope_context_text(runtime_context),
            )
            compression_service = self._build_history_compression_service(
                run_model=run_model,
                agent_id=agent_id,
                model=model,
                model_settings=model_settings,
                context_budget=context_budget,
                context_processor=context_processor,
            )
            resolved_history_processors = list(history_processors or ())
            if context_processor is not None:
                async def context_history_processor(messages: list[Any]) -> list[Any]:
                    """在每次模型请求前执行预算触发的上下文压缩。"""

                    return await context_processor.process(
                        None,
                        messages,
                        compression_service=compression_service,
                    )

                resolved_history_processors.append(context_history_processor)
            agent = Agent(
                model,
                name=agent_id,
                output_type=[str, DeferredToolRequests],
                instructions=instructions,
                deps_type=AgentToolDeps if deps is not None else type(None),
                tools=tools or (),
                history_processors=resolved_history_processors,
            )
            projector = PydanticEventProjector(
                run_id=run_model.run_id,
                session_id=run_model.session_id,
                append_event=lambda event: self._store.append_event(run_model, event),
                deferred_tool_results=deferred_tool_results,
                final_messages=final_messages,
                final_message_image_refs=message_image_refs,
                on_message_delta=content_parts.append,
                on_reasoning_delta=reasoning_parts.append,
            )
            async with agent.iter(
                message if message else None,
                model_settings=model_settings or None,
                deps=deps,
                message_history=message_history,
                deferred_tool_results=deferred_tool_results,
                infer_name=False,
            ) as agent_run:
                async for node in agent_run:
                    should_stop, should_cancel = await self._cancel_event_if_requested(run_model)
                    if should_stop:
                        async for sse in self._flush_projector_buffer(projector, best_effort=True):
                            yield sse
                        if not should_cancel:
                            return
                        event = await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
                        yield encode_sse_event(event)
                        return
                    if agent.is_model_request_node(node):
                        yield await self._yield_and_store(
                            run_model,
                            AgentRunEvent(event="model.request.started", run_id=run_model.run_id, session_id=run_model.session_id),
                        )
                        async with node.stream(agent_run.ctx) as stream:
                            async for raw_event in self._iter_stream_events(stream, run_model=run_model):
                                should_stop, should_cancel = await self._cancel_event_if_requested(run_model)
                                if should_stop:
                                    async for sse in self._flush_projector_buffer(projector, best_effort=True):
                                        yield sse
                                    if not should_cancel:
                                        return
                                    event = await self._store.mark_terminal(
                                        run_model,
                                        status="cancelled",
                                        content="用户停止了当前运行。",
                                    )
                                    yield encode_sse_event(event)
                                    return
                                for event in await projector.handle_raw_event(raw_event):
                                    yield encode_sse_event(event)
                        async for sse in self._flush_projector_buffer(projector):
                            yield sse
                        await self._sync_run_message_history(
                            run_model=run_model,
                            agent_id=agent_id,
                            base_run_message_history=base_run_message_history,
                            previous_message_history_count=previous_message_history_count,
                            final_messages=final_messages,
                            agent_run=agent_run,
                            context_budget=context_budget,
                            context_processor=context_processor,
                            message_image_refs=message_image_refs,
                        )
                        yield await self._yield_and_store(
                            run_model,
                            AgentRunEvent(event="model.request.completed", run_id=run_model.run_id, session_id=run_model.session_id),
                        )
                        async for sse in self._emit_context_status(
                            run_model=run_model,
                            agent_id=agent_id,
                            context_budget=context_budget,
                            context_processor=context_processor,
                            final_messages=final_messages,
                        ):
                            yield sse
                        continue
                    if agent.is_call_tools_node(node):
                        async with node.stream(agent_run.ctx) as stream:
                            async for raw_event in self._iter_stream_events(
                                stream,
                                run_model=run_model,
                                idle_timeout_seconds=self._tool_stream_idle_timeout_seconds,
                                refresh_timeout_on_run_activity=True,
                            ):
                                should_stop, should_cancel = await self._cancel_event_if_requested(run_model)
                                if should_stop:
                                    async for sse in self._flush_projector_buffer(projector, best_effort=True):
                                        yield sse
                                    if not should_cancel:
                                        return
                                    event = await self._store.mark_terminal(
                                        run_model,
                                        status="cancelled",
                                        content="用户停止了当前运行。",
                                    )
                                    yield encode_sse_event(event)
                                    return
                                for event in await projector.handle_raw_event(raw_event):
                                    yield encode_sse_event(event)
                if agent_run.result is None:
                    raise RuntimeError("Pydantic AI run finished without result")
                final_messages[:] = _merge_run_message_history(
                    base_run_message_history,
                    self._safe_run_messages_with_image_refs(
                        agent_run.result,
                        message_image_refs,
                        previous_message_count=previous_message_history_count,
                    ),
                )
                if context_processor is not None:
                    context_processor.record_message_history(final_messages)
                output = getattr(agent_run.result, "output", None)
                if isinstance(output, DeferredToolRequests):
                    async for sse in self._flush_projector_buffer(projector):
                        yield sse
                    event = await self._pause_for_deferred_tools(
                        run_model,
                        output,
                        final_messages=final_messages,
                        context_processor=context_processor,
                    )
                    yield encode_sse_event(event)
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
            await self._store.append_assistant_message(
                run_model,
                content="".join(content_parts),
                reasoning_content="".join(reasoning_parts) or None,
                message_history=final_messages,
            )
            await self._compress_completed_run_if_required(
                run_model=run_model,
                agent_id=agent_id,
                agent_result=agent_run.result,
                context_processor=context_processor,
                compression_service=compression_service,
            )
            event = await self._store.mark_terminal(run_model, status="completed", content="".join(content_parts) or None)
            yield encode_sse_event(event)
        except MemberDelegationPaused as exc:
            async for sse in self._flush_projector_buffer(projector, best_effort=True):
                yield sse
            await self._store.save_run_message_history(
                run_model,
                _merge_run_message_history(base_run_message_history, final_messages),
            )
            event = await self._store.pause_for_requirement(run_model, requirement=exc.requirement)
            yield encode_sse_event(event)
        except AppException as exc:
            async for sse in self._flush_projector_buffer(projector, best_effort=True):
                yield sse
            if exc.code == "AI_RUN_CANCELLED":
                event = await self._store.mark_terminal(run_model, status="cancelled", content="用户停止了当前运行。")
                yield encode_sse_event(event)
                return
            logger.warning(
                "Agent run stopped by application error",
                extra=build_agent_error_log_extra(
                    exc,
                    event="ai.agent_run.app_error",
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                    agent_id=agent_id,
                    error_code=exc.code,
                    user_error_message=exc.detail,
                ),
            )
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
                extra=build_agent_error_log_extra(
                    exc,
                    event="ai.agent_run.exception",
                    run_id=run_model.run_id,
                    session_id=run_model.session_id,
                    agent_id=agent_id,
                    error_code=failure.code,
                    user_error_message=failure.message,
                    raw_error_message=failure.raw_message,
                ),
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
        *,
        final_messages: list[dict[str, Any]] | None = None,
        context_processor: AgentContextLimitProcessor | None = None,
    ) -> AgentRunEvent:
        """把 Pydantic AI deferred 请求转换为平台暂停事件。"""

        if final_messages is not None:
            if context_processor is not None:
                context_processor.record_message_history(final_messages)
            await self._store.save_run_message_history(run_model, final_messages, commit=False)
        return await self._store.pause_for_requirement(
            run_model,
            requirement=_requirement_from_deferred(
                requests,
                run_id=run_model.run_id,
                session_id=run_model.session_id,
            ),
        )

    async def _sync_run_message_history(
        self,
        *,
        run_model: AiAgentRun,
        agent_id: str,
        base_run_message_history: list[dict[str, Any]],
        previous_message_history_count: int,
        final_messages: list[dict[str, Any]],
        agent_run: Any,
        context_budget: AgentHistoryBudget | None,
        context_processor: AgentContextLimitProcessor | None,
        message_image_refs: list[dict[str, Any]] | None,
    ) -> None:
        """每次模型响应后替换 run 消息快照，并刷新真实 usage 高水位。"""

        _ = agent_id, context_budget
        if agent_run.result is not None:
            new_messages = self._safe_run_messages_with_image_refs(
                agent_run.result,
                message_image_refs,
                previous_message_count=previous_message_history_count,
            )
        else:
            new_messages = self._safe_run_messages_with_image_refs(
                agent_run,
                message_image_refs,
                previous_message_count=previous_message_history_count,
            )
        messages = _merge_run_message_history(base_run_message_history, new_messages)
        final_messages[:] = messages
        if context_processor is not None:
            context_processor.record_message_history(final_messages)
        await self._store.save_run_message_history(run_model, final_messages, commit=False)

    def _build_history_compression_service(
        self,
        *,
        run_model: AiAgentRun,
        agent_id: str,
        model: Any,
        model_settings: dict[str, Any],
        context_budget: AgentHistoryBudget | None,
        context_processor: AgentContextLimitProcessor | None,
    ) -> HistoryCompressionService | None:
        """按当前 run 和模型构造上下文压缩服务。"""

        if context_budget is None or context_processor is None:
            return None
        return HistoryCompressionService(
            session=context_processor.session,
            user_id=context_processor.user_id,
            session_id=context_processor.session_id,
            agent_id=agent_id,
            store=self._store,
            run_model=run_model,
            budget=context_budget,
            model=model,
            model_settings=model_settings,
            latest_usage=lambda: context_processor.latest_usage,
            retained_message_count=lambda: context_processor.history_prefix_message_count,
        )

    async def _compress_completed_run_if_required(
        self,
        *,
        run_model: AiAgentRun,
        agent_id: str,
        agent_result: Any,
        context_processor: AgentContextLimitProcessor | None,
        compression_service: HistoryCompressionService | None,
    ) -> None:
        """最终响应后若仍超预算，则同步压缩稳定历史供下一轮使用。"""

        _ = agent_id
        if context_processor is None or compression_service is None:
            return
        usage = context_processor.latest_usage
        if usage.context_used_tokens <= 0:
            return
        if usage.context_used_tokens < context_processor.budget.context_input_budget_tokens:
            return
        raw_messages = _safe_messages(agent_result) if agent_result is not None else []
        if not raw_messages:
            return
        try:
            messages = list(ModelMessagesTypeAdapter.validate_python(raw_messages))
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to validate final messages before history compression",
                extra={"run_id": run_model.run_id, "session_id": run_model.session_id},
            )
            return
        await context_processor.compress_completed_messages(
            messages=messages,
            current_run_id=run_model.run_id,
            compression_service=compression_service,
            fail_on_error=False,
        )

    async def _emit_context_status(
        self,
        *,
        run_model: AiAgentRun,
        agent_id: str,
        context_budget: AgentHistoryBudget | None,
        context_processor: AgentContextLimitProcessor | None,
        final_messages: list[dict[str, Any]],
    ) -> AsyncGenerator[bytes, None]:
        """写入每次模型响应后的上下文状态事件。"""

        if context_budget is None:
            return
        status = build_context_status_item(
            session_id=run_model.session_id,
            agent_id=agent_id,
            budget=context_budget,
            message_json=final_messages,
            summary_json=context_processor.summary_json if context_processor is not None else None,
        )
        event = await self._store.append_event(
            run_model,
            AgentRunEvent(
                event="context.status",
                run_id=run_model.run_id,
                session_id=run_model.session_id,
                data=status.model_dump(mode="json"),
            ),
        )
        yield encode_sse_event(event)

    @staticmethod
    def _safe_new_messages_with_image_refs(result: Any, image_refs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """安全读取当前 run 新消息，并统一脱敏图片引用。"""

        from app.ai.image_refs import sanitize_message_history_image_refs

        return sanitize_message_history_image_refs(
            safe_new_messages(result),
            image_refs=image_refs,
        )

    @staticmethod
    def _safe_run_messages_with_image_refs(
        result: Any,
        image_refs: list[dict[str, Any]] | None,
        *,
        previous_message_count: int,
    ) -> list[dict[str, Any]]:
        """按传入历史长度截取当前平台 run 快照，兼容 paused run 恢复后的完整保存。"""

        from app.ai.image_refs import sanitize_message_history_image_refs

        all_messages = safe_messages(result)
        if all_messages and len(all_messages) >= previous_message_count:
            return sanitize_message_history_image_refs(
                all_messages[previous_message_count:],
                image_refs=image_refs,
            )
        return sanitize_message_history_image_refs(
            safe_new_messages(result),
            image_refs=image_refs,
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

    async def _iter_stream_events(
        self,
        stream: Any,
        *,
        run_model: AiAgentRun | None = None,
        idle_timeout_seconds: float | None = None,
        refresh_timeout_on_run_activity: bool = False,
    ) -> AsyncGenerator[Any, None]:
        """按指定空闲超时消费节点流；工具等待可把成员事件视为活动心跳。"""

        iterator = stream.__aiter__()
        pending_event_task: asyncio.Task[Any] | None = None
        wait_started_at = monotonic()
        activity_version = (
            get_live_run_activity_version(run_model.run_id)
            if run_model is not None and refresh_timeout_on_run_activity
            else 0
        )
        timeout_seconds = (
            float(idle_timeout_seconds)
            if idle_timeout_seconds is not None
            else self._stream_idle_timeout_seconds
        )
        try:
            while True:
                if run_model is not None and refresh_timeout_on_run_activity:
                    current_activity_version = get_live_run_activity_version(run_model.run_id)
                    if current_activity_version != activity_version:
                        activity_version = current_activity_version
                        wait_started_at = monotonic()
                if pending_event_task is None:
                    pending_event_task = asyncio.create_task(iterator.__anext__())
                    wait_started_at = monotonic()

                elapsed = monotonic() - wait_started_at
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    await self._cancel_pending_stream_task(pending_event_task)
                    pending_event_task = None
                    raise AppException(
                        status_code=504,
                        code="AI_AGENT_STREAM_IDLE_TIMEOUT",
                        detail="模型或工具流长时间没有返回新事件，本次运行已停止。",
                    )

                done, _ = await asyncio.wait(
                    {pending_event_task},
                    timeout=min(_STREAM_CONTROL_POLL_INTERVAL_SECONDS, remaining),
                )
                if not done:
                    if run_model is not None:
                        should_stop, should_cancel = await self._cancel_event_if_requested(run_model)
                        if should_stop:
                            await self._cancel_pending_stream_task(pending_event_task)
                            pending_event_task = None
                            if should_cancel:
                                raise AppException(
                                    status_code=409,
                                    code="AI_RUN_CANCELLED",
                                    detail="当前智能体运行已被取消。",
                                )
                            return
                    continue

                completed_task = pending_event_task
                pending_event_task = None
                try:
                    raw_event = completed_task.result()
                except StopAsyncIteration:
                    return
                yield raw_event
        finally:
            if pending_event_task is not None:
                await self._cancel_pending_stream_task(pending_event_task)

    async def _cancel_pending_stream_task(self, task: asyncio.Task[Any]) -> None:
        """取消底层流或后台运行任务，且不让不响应取消的任务阻塞终态写入。"""

        if task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self._stream_cancel_grace_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "Agent stream event task did not stop after cancellation grace period",
                extra={"event": "ai.agent_stream.cancel_timeout"},
            )
            task.add_done_callback(_consume_detached_task_result)
        except asyncio.CancelledError:
            if task.done():
                return
            raise

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


def _consume_detached_task_result(task: asyncio.Task[Any]) -> None:
    """回收已脱离等待链的底层流任务结果，避免异步任务异常无人读取。"""

    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001
        logger.debug("Detached agent stream task finished with an exception", exc_info=True)


def _merge_run_message_history(
    base_message_history: list[dict[str, Any]],
    new_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """合并 paused run 继续前历史与本次新增消息，避免工具返回覆盖前置工具调用。"""

    base = _message_dicts(base_message_history)
    latest = _message_dicts(new_messages)
    if base and latest[: len(base)] == base:
        return latest
    return [*base, *latest]


def _message_dicts(value: list[Any]) -> list[dict[str, Any]]:
    """过滤消息历史中的非对象项，避免坏数据污染保存链路。"""

    return [dict(item) for item in value if isinstance(item, dict)]


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
