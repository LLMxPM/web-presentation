"""文件功能：承载 AgentSessionFacade 的 Agno 流式事件转换、raw SSE 透传和事件归一化逻辑。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput

from app.ai.agent import AgentRuntimeContext
from app.ai.session_facade_common import (
    _coerce_str,
    _event_payload,
    _extract_member_event_data,
    _extract_text_content,
    _extract_tool_error_info,
    _normalize_raw_event_payload,
    _raw_event_name,
    _raw_event_text_content,
    _resolve_reasoning_content,
    _run_latest_event_index_from_detail,
    _split_reasoning_content,
    _stringify_content,
)
from app.ai.session_facade_models import (
    _TERMINAL_RUN_EVENTS,
    _ActiveAgentStream,
    _RawSseRunMessageTracker,
    _StreamingHistoryTracker,
)
from app.ai.session_facade_requirements import _extract_pending_requirement
from app.ai.session_facade_sse import (
    _close_async_iterator,
    _ensure_sse_bytes,
    _finish_shielded_cleanup,
    _format_raw_sse_error,
    _iter_raw_sse_payloads,
    _raw_terminal_content,
)
from app.core.exceptions import AppException
from app.schemas.agent import AgentRunEvent, AgentScopeContext


class _SessionFacadeStreamMixin:
    """提供流式事件处理方法，依赖主 Facade 的会话读写与运行状态方法。"""

    def _stream_agno_events(
        self,
        *,
        agent_id: str,
        session_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        stream_builder,
        reserved_lock: asyncio.Lock | None = None,
        initial_history_messages: list[Any] | None = None,
        resolved_tool_execution: dict[str, Any] | None = None,
    ) -> AsyncGenerator[AgentRunEvent, None]:
        """把 Agno 事件流重写为前端稳定消费的统一事件。"""

        async def generator() -> AsyncGenerator[AgentRunEvent, None]:
            active_run_id: str | None = None
            active_stream: _ActiveAgentStream | None = None
            terminal_seen = False
            history_tracker = _StreamingHistoryTracker(initial_history_messages)
            lock = reserved_lock or self._get_session_run_lock(session_id=session_id, agent_id=agent_id)
            lock_acquired = reserved_lock is not None
            if not lock_acquired:
                if lock.locked():
                    yield AgentRunEvent(
                        event="run.error",
                        session_id=session_id,
                        data={"message": "当前会话已有运行中的智能体任务。", "code": "AI_SESSION_RUN_ACTIVE"},
                    )
                    return
                await lock.acquire()
                lock_acquired = True
            try:
                await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
                active_stream = await stream_builder()
                active_run_id = active_stream.run_id
                yield await self._build_context_status_event(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    runtime_context=runtime_context,
                    run_id=active_run_id,
                    extra_history_messages=history_tracker.snapshot(),
                )
                async for raw_event in active_stream.stream:
                    raw_payload = _normalize_raw_event_payload(raw_event)
                    raw_event_name = _raw_event_name(raw_event, raw_payload)
                    normalized_event = self._normalize_event(
                        raw_event=raw_event,
                        runtime_context=runtime_context,
                        session_id=session_id,
                    )
                    if raw_event_name in {"RunContentCompleted", "RunContentCompletedEvent", "TeamRunContentCompleted"}:
                        if history_tracker.flush_assistant_content(_raw_event_text_content(raw_payload)):
                            yield await self._build_context_status_event(
                                session_id=session_id,
                                agent_id=agent_id,
                                scope=scope,
                                runtime_context=runtime_context,
                                run_id=active_run_id,
                                extra_history_messages=history_tracker.snapshot(),
                            )
                    if normalized_event is not None:
                        if normalized_event.event in {"run.started", "run.continued"} and normalized_event.run_id:
                            active_run_id = normalized_event.run_id
                        if normalized_event.event in _TERMINAL_RUN_EVENTS:
                            terminal_seen = True
                            history_tracker.flush_assistant_content(normalized_event.content)
                            if normalized_event.event == "run.cancelled" and active_run_id:
                                await self._preserve_cancelled_raw_run_messages(
                                    session_id=session_id,
                                    agent_id=agent_id,
                                    run_id=active_run_id,
                                    fallback_user_message=history_tracker.fallback_user_content,
                                    assistant_content=history_tracker.assistant_content,
                                    reasoning_content=history_tracker.reasoning_content,
                                )
                            if (
                                normalized_event.event == "run.completed"
                                and active_run_id
                                and resolved_tool_execution is not None
                            ):
                                await self._normalize_agno_completed_run_after_continue(
                                    session_id=session_id,
                                    agent_id=agent_id,
                                    run_id=active_run_id,
                                    content=normalized_event.content,
                                    resolved_tool_execution=resolved_tool_execution,
                                )
                            yield await self._build_context_status_event(
                                session_id=session_id,
                                agent_id=agent_id,
                                scope=scope,
                                runtime_context=runtime_context,
                                run_id=active_run_id,
                                extra_history_messages=history_tracker.snapshot(),
                            )
                            yield normalized_event
                            if normalized_event.event == "run.paused":
                                break
                            continue
                        if normalized_event.event == "message.delta":
                            history_tracker.append_assistant_delta(
                                normalized_event.content,
                                _coerce_str((normalized_event.data or {}).get("reasoning_content")),
                            )
                        elif normalized_event.event == "tool.started":
                            history_tracker.remember_tool_started(normalized_event)
                        elif normalized_event.event in {"tool.completed", "tool.error"}:
                            history_tracker.append_tool_event(normalized_event)
                        yield normalized_event
                        if normalized_event.event in {"tool.completed", "tool.error"}:
                            yield await self._build_context_status_event(
                                session_id=session_id,
                                agent_id=agent_id,
                                scope=scope,
                                runtime_context=runtime_context,
                                run_id=active_run_id,
                                extra_history_messages=history_tracker.snapshot(),
                            )
            except asyncio.CancelledError:
                raise
            except AppException as exc:
                terminal_seen = True
                if active_run_id:
                    await self._mark_run_terminal(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=active_run_id,
                        status=RunStatus.error,
                        content=exc.detail,
                    )
                yield AgentRunEvent(
                    event="run.error",
                    session_id=session_id,
                    data={"message": exc.detail, "code": exc.code},
                )
            except Exception:  # noqa: BLE001
                terminal_seen = True
                if active_run_id:
                    await self._mark_run_terminal(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=active_run_id,
                        status=RunStatus.error,
                        content="智能体执行失败，请稍后重试。",
                    )
                yield AgentRunEvent(
                    event="run.error",
                    session_id=session_id,
                    data={"message": "智能体执行失败，请稍后重试。"},
                )
            finally:
                cleanup_cancelled = False
                try:
                    if active_stream is not None:
                        try:
                            cleanup_cancelled = await _finish_shielded_cleanup(
                                _close_async_iterator(active_stream.stream)
                            ) or cleanup_cancelled
                        except Exception:  # noqa: BLE001
                            pass
                    if active_run_id and not terminal_seen:
                        cleanup_cancelled = await _finish_shielded_cleanup(
                            self._mark_run_terminal(
                                session_id=session_id,
                                agent_id=agent_id,
                                run_id=active_run_id,
                                status=RunStatus.cancelled,
                                content="流式连接已断开，本次运行已停止。",
                            )
                        ) or cleanup_cancelled
                        if history_tracker.has_preservable_content:
                            cleanup_cancelled = await _finish_shielded_cleanup(
                                self._preserve_cancelled_raw_run_messages(
                                    session_id=session_id,
                                    agent_id=agent_id,
                                    run_id=active_run_id,
                                    fallback_user_message=history_tracker.fallback_user_content,
                                    assistant_content=history_tracker.assistant_content,
                                    reasoning_content=history_tracker.reasoning_content,
                                )
                            ) or cleanup_cancelled
                finally:
                    if lock_acquired and lock.locked():
                        lock.release()
                if cleanup_cancelled:
                    raise asyncio.CancelledError

        return generator()


    def _stream_agno_raw_sse(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        stream_builder,
        reserved_lock: asyncio.Lock | None = None,
        fallback_user_message: str | None = None,
        expected_run_id: str | None = None,
        resolved_tool_execution: dict[str, Any] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """执行 Agno background stream，并直接透传 Agno 生成的 SSE 文本。"""

        async def generator() -> AsyncGenerator[bytes, None]:
            tracker = _RawSseRunMessageTracker(fallback_user_message=fallback_user_message)
            active_run_id: str | None = expected_run_id
            active_stream: _ActiveAgentStream | None = None
            tracker.run_id = expected_run_id
            raw_string_seen = False
            synced_terminal_status: RunStatus | None = None
            lock = reserved_lock or self._get_session_run_lock(session_id=session_id, agent_id=agent_id)
            lock_acquired = reserved_lock is not None
            if not lock_acquired:
                if lock.locked():
                    yield _format_raw_sse_error(
                        run_id=None,
                        session_id=session_id,
                        message="当前会话已有运行中的智能体任务。",
                        code="AI_SESSION_RUN_ACTIVE",
                    )
                    return
                await lock.acquire()
                lock_acquired = True
            try:
                session_detail = await self.ensure_session_access(session_id=session_id, agent_id=agent_id, scope=scope)
                active_stream = await stream_builder()
                active_run_id = active_stream.run_id
                tracker.run_id = active_run_id
                local_event_index = _run_latest_event_index_from_detail(session_detail, active_run_id)
                async for sse_data in active_stream.stream:
                    if isinstance(sse_data, (str, bytes)):
                        raw_string_seen = True
                        raw_bytes = _ensure_sse_bytes(sse_data)
                        for raw_payload, raw_event_name in _iter_raw_sse_payloads(raw_bytes):
                            tracker.observe_payload(raw_payload, event_name=raw_event_name, fallback_run_id=active_run_id)
                            active_run_id = tracker.run_id or active_run_id
                            synced_terminal_status = await self._sync_raw_terminal_status_if_needed(
                                session_id=session_id,
                                agent_id=agent_id,
                                run_id=active_run_id,
                                status=tracker.terminal_status,
                                previous_status=synced_terminal_status,
                                content=_raw_terminal_content(raw_payload),
                                resolved_tool_execution=resolved_tool_execution,
                            )
                        yield raw_bytes
                        if synced_terminal_status == RunStatus.paused:
                            break
                    else:
                        from agno.os.utils import format_sse_event_with_index

                        raw_payload = _normalize_raw_event_payload(sse_data)
                        raw_event_name = _raw_event_name(sse_data, raw_payload)
                        local_event_index += 1
                        tracker.observe_payload(raw_payload, event_name=raw_event_name, fallback_run_id=active_stream.run_id)
                        active_run_id = tracker.run_id or active_run_id
                        synced_terminal_status = await self._sync_raw_terminal_status_if_needed(
                            session_id=session_id,
                            agent_id=agent_id,
                            run_id=active_run_id,
                            status=tracker.terminal_status,
                            previous_status=synced_terminal_status,
                            content=_raw_terminal_content(raw_payload),
                            resolved_tool_execution=resolved_tool_execution,
                        )
                        yield _ensure_sse_bytes(
                            format_sse_event_with_index(
                                sse_data,
                                event_index=local_event_index,
                                run_id=active_stream.run_id,
                            )
                        )
                        if synced_terminal_status == RunStatus.paused:
                            break
                if (
                    synced_terminal_status != RunStatus.paused
                    and (raw_string_seen or tracker.cancelled)
                    and (tracker.run_id or active_run_id)
                ):
                    await self._preserve_cancelled_raw_run_messages(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=str(tracker.run_id or active_run_id),
                        fallback_user_message=tracker.fallback_user_message,
                        assistant_content=tracker.assistant_content,
                        reasoning_content=tracker.reasoning_content,
                    )
            except asyncio.CancelledError:
                raise
            except AppException as exc:
                error_run_id = tracker.run_id or active_run_id or expected_run_id
                if error_run_id:
                    await self._mark_run_terminal(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=error_run_id,
                        status=RunStatus.error,
                        content=exc.detail,
                        resolved_tool_execution=resolved_tool_execution,
                    )
                yield _format_raw_sse_error(
                    run_id=error_run_id,
                    session_id=session_id,
                    message=exc.detail,
                    code=exc.code,
                )
            except Exception:  # noqa: BLE001
                error_run_id = tracker.run_id or active_run_id or expected_run_id
                if error_run_id:
                    await self._mark_run_terminal(
                        session_id=session_id,
                        agent_id=agent_id,
                        run_id=error_run_id,
                        status=RunStatus.error,
                        content="智能体执行失败，请稍后重试。",
                        resolved_tool_execution=resolved_tool_execution,
                    )
                yield _format_raw_sse_error(
                    run_id=error_run_id,
                    session_id=session_id,
                    message="智能体执行失败，请稍后重试。",
                    code="AI_RUN_FAILED",
                )
            finally:
                if active_stream is not None and synced_terminal_status == RunStatus.paused:
                    try:
                        await _close_async_iterator(active_stream.stream)
                    except Exception:  # noqa: BLE001
                        pass
                if lock_acquired and lock.locked():
                    lock.release()

        return generator()


    async def _sync_raw_terminal_status_if_needed(
        self,
        *,
        session_id: str,
        agent_id: str,
        run_id: str | None,
        status: RunStatus | None,
        previous_status: RunStatus | None,
        content: str | None,
        resolved_tool_execution: dict[str, Any] | None,
    ) -> RunStatus | None:
        """raw SSE 看到终态时，把已解决 HITL 的残留状态同步回 Agno session。"""

        if status is None or status == previous_status or not run_id:
            return previous_status
        if status == RunStatus.completed and resolved_tool_execution is not None:
            await self._normalize_agno_completed_run_after_continue(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                content=content,
                resolved_tool_execution=resolved_tool_execution,
            )
        elif status == RunStatus.paused:
            await self._set_existing_run_status(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                status=RunStatus.paused,
                content=content,
            )
        elif status in {RunStatus.cancelled, RunStatus.error} and resolved_tool_execution is not None:
            await self._mark_run_terminal(
                session_id=session_id,
                agent_id=agent_id,
                run_id=run_id,
                status=status,
                content=content or ("运行已停止。" if status == RunStatus.cancelled else "智能体执行失败，请稍后重试。"),
                resolved_tool_execution=resolved_tool_execution,
            )
        return status


    async def _build_context_status_event(
        self,
        *,
        session_id: str,
        agent_id: str,
        scope: AgentScopeContext,
        runtime_context: AgentRuntimeContext,
        run_id: str | None,
        extra_history_messages: list[Any] | None = None,
    ) -> AgentRunEvent:
        """把上下文预算状态包装成前端可消费的 SSE 事件。"""

        status = await self.get_context_status(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            runtime_context=runtime_context,
            extra_history_messages=extra_history_messages,
        )
        return AgentRunEvent(
            event="context.status",
            run_id=run_id,
            session_id=session_id,
            data=status.model_dump(mode="json"),
        )


    def _normalize_event(
        self,
        *,
        raw_event: Any,
        runtime_context: AgentRuntimeContext,
        session_id: str,
    ) -> AgentRunEvent | None:
        """把 Agno 原始事件翻译成 Editor 约定的事件协议。"""

        payload = _event_payload(raw_event)
        if not isinstance(payload, dict):
            return None

        event_name = str(payload.get("event") or type(raw_event).__name__)
        run_id = payload.get("run_id")
        resolved_session_id = payload.get("session_id") or session_id
        member_event_data = _extract_member_event_data(payload)
        is_member_event = bool(member_event_data.get("parent_run_id") and member_event_data.get("member_run_id"))
        event_run_id = member_event_data.get("parent_run_id") if is_member_event else run_id

        if isinstance(raw_event, (RunOutput, TeamRunOutput)):
            pending_requirement = _extract_pending_requirement(
                payload={**payload, "run_id": event_run_id} if event_run_id else payload,
                runtime_context=runtime_context,
            )
            if pending_requirement is not None:
                return AgentRunEvent(
                    event="run.paused",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={
                        "requirement": pending_requirement.model_dump(mode="json"),
                        **member_event_data,
                    },
                )
            if is_member_event and not isinstance(raw_event, TeamRunOutput):
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload),
            )
            return AgentRunEvent(
                event="run.completed",
                run_id=event_run_id,
                session_id=resolved_session_id,
                content=content,
                data={
                    "metadata": payload.get("metadata") or {},
                    "reasoning_content": reasoning_content,
                    **member_event_data,
                },
            )

        if event_name in {"RunStarted", "RunStartedEvent", "TeamRunStarted"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            return AgentRunEvent(
                event="run.started",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={"agent_id": payload.get("agent_id") or payload.get("team_id"), **member_event_data},
            )

        if event_name in {
            "RunContent",
            "RunContentEvent",
            "IntermediateRunContent",
            "IntermediateRunContentEvent",
            "RunIntermediateContent",
            "TeamRunContent",
            "TeamRunIntermediateContent",
        }:
            if is_member_event:
                return None
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload, preserve_stream_boundary=True),
                preserve_reasoning_boundary=True,
            )
            if not content and not reasoning_content:
                return None
            return AgentRunEvent(
                event="message.delta",
                run_id=event_run_id,
                session_id=resolved_session_id,
                content=content,
                data={"reasoning_content": reasoning_content, **member_event_data},
            )

        if event_name in {"ToolCallStarted", "ToolCallStartedEvent", "TeamToolCallStarted"}:
            tool_execution = payload.get("tool") or {}
            return AgentRunEvent(
                event="tool.started",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "tool_name": tool_execution.get("tool_name"),
                    "tool_call_id": tool_execution.get("tool_call_id"),
                    "tool_args": tool_execution.get("tool_args") or {},
                    **member_event_data,
                },
            )

        if event_name in {"ToolCallCompleted", "ToolCallCompletedEvent", "TeamToolCallCompleted"}:
            tool_execution = payload.get("tool") or {}
            tool_result = tool_execution.get("result")
            if tool_result is None:
                tool_result = payload.get("content")
            return AgentRunEvent(
                event="tool.completed",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "tool_name": tool_execution.get("tool_name"),
                    "tool_call_id": tool_execution.get("tool_call_id"),
                    "result": tool_result,
                    "message": payload.get("content"),
                    **member_event_data,
                },
            )

        if event_name in {"ToolCallError", "ToolCallErrorEvent", "TeamToolCallError"}:
            tool_execution = payload.get("tool") or {}
            error_message, error_code, repair_attempted, repair_succeeded, repair_reason = _extract_tool_error_info(
                payload=payload,
                tool_execution=tool_execution,
            )
            return AgentRunEvent(
                event="tool.error",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "tool_name": tool_execution.get("tool_name"),
                    "tool_call_id": tool_execution.get("tool_call_id"),
                    "message": error_message,
                    "code": error_code,
                    "repair_attempted": repair_attempted,
                    "repair_succeeded": repair_succeeded,
                    "repair_reason": repair_reason,
                    **member_event_data,
                },
            )

        if event_name in {"RunPaused", "RunPausedEvent", "TeamRunPaused"}:
            pending_requirement = _extract_pending_requirement(
                payload={**payload, "run_id": event_run_id} if event_run_id else payload,
                runtime_context=runtime_context,
            )
            return AgentRunEvent(
                event="run.paused",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={
                    "requirement": pending_requirement.model_dump(mode="json") if pending_requirement else None,
                    **member_event_data,
                },
            )

        if event_name in {"RunContinued", "RunContinuedEvent", "TeamRunContinued"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            return AgentRunEvent(
                event="run.continued",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data=member_event_data,
            )

        if event_name in {"RunContentCompleted", "RunContentCompletedEvent", "TeamRunContentCompleted"}:
            return None

        if event_name in {"RunCompleted", "RunCompletedEvent", "TeamRunCompleted"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            completed_content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload),
            )
            return AgentRunEvent(
                event="run.completed",
                run_id=event_run_id,
                session_id=resolved_session_id,
                content=completed_content,
                data={
                    "metadata": payload.get("metadata") or {},
                    "reasoning_content": reasoning_content,
                    **member_event_data,
                },
            )

        if event_name in {"RunCancelled", "RunCancelledEvent", "TeamRunCancelled"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={"source_event": event_name, "member_event": True, **member_event_data},
                )
            return AgentRunEvent(
                event="run.cancelled",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={"message": _stringify_content(payload.get("content") or payload.get("message") or payload.get("reason")), **member_event_data},
            )

        if event_name in {"RunError", "RunErrorEvent", "TeamRunError"}:
            if is_member_event:
                return AgentRunEvent(
                    event="trace.event",
                    run_id=event_run_id,
                    session_id=resolved_session_id,
                    data={
                        "source_event": event_name,
                        "member_event": True,
                        "message": _stringify_content(payload.get("content") or payload.get("error")),
                        **member_event_data,
                    },
                )
            return AgentRunEvent(
                event="run.error",
                run_id=event_run_id,
                session_id=resolved_session_id,
                data={"message": _stringify_content(payload.get("content") or payload.get("error")), **member_event_data},
            )

        return AgentRunEvent(
            event="trace.event",
            run_id=event_run_id,
            session_id=resolved_session_id,
            data={"source_event": event_name, "payload": payload, **member_event_data},
        )
