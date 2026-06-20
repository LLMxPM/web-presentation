"""文件功能：将 Pydantic AI 原始流式事件投影为平台 AgentRunEvent。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from pydantic_ai import AgentRunResultEvent, DeferredToolRequests, DeferredToolResults, ToolDenied
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
)

from app.ai.image_refs import sanitize_message_history_image_refs
from app.ai.platform_tools import is_recoverable_tool_error_result
from app.schemas.agent import AgentRunEvent

logger = logging.getLogger(__name__)

_MESSAGE_DELTA_FLUSH_INTERVAL_SECONDS = 0.5
_REASONING_DELTA_FLUSH_INTERVAL_SECONDS = 1.5
_MESSAGE_DELTA_FLUSH_BYTES = 4 * 1024
_REASONING_DELTA_FLUSH_BYTES = 8 * 1024

_AppendEvent = Callable[[AgentRunEvent], Awaitable[AgentRunEvent]]
_BaseEventData = Callable[[], dict[str, Any]]
_DeltaCallback = Callable[[str], None]
_DeferredHandler = Callable[[DeferredToolRequests, list[dict[str, Any]]], Awaitable[AgentRunEvent | None]]
_ToolCallIdMapper = Callable[[str | None], Any]
_ToolExtraData = Callable[[str | None], dict[str, Any]]


class PydanticEventProjector:
    """复用同一套规则投影普通 run 和成员 run 的 Pydantic AI 原始事件。"""

    def __init__(
        self,
        *,
        run_id: str,
        session_id: str,
        append_event: _AppendEvent,
        deferred_tool_results: DeferredToolResults | None = None,
        event_prefix: str = "",
        base_event_data: _BaseEventData | None = None,
        map_tool_call_id: _ToolCallIdMapper | None = None,
        extra_tool_data: _ToolExtraData | None = None,
        final_messages: list[dict[str, Any]] | None = None,
        final_message_image_refs: list[dict[str, Any]] | None = None,
        on_message_delta: _DeltaCallback | None = None,
        on_reasoning_delta: _DeltaCallback | None = None,
        on_deferred: _DeferredHandler | None = None,
    ) -> None:
        """保存投影配置；事件前缀用于生成 member.* 等命名空间事件。"""

        self._run_id = run_id
        self._session_id = session_id
        self._append_event = append_event
        self._event_prefix = event_prefix
        self._base_event_data = base_event_data or (lambda: {})
        self._map_tool_call_id = map_tool_call_id or (lambda raw_tool_call_id: raw_tool_call_id)
        self._extra_tool_data = extra_tool_data or (lambda raw_tool_call_id: {})
        self._final_messages = final_messages if final_messages is not None else []
        self._final_message_image_refs = list(final_message_image_refs or [])
        self._on_message_delta = on_message_delta
        self._on_reasoning_delta = on_reasoning_delta
        self._on_deferred = on_deferred
        self._denied_tool_call_ids = denied_tool_call_ids(deferred_tool_results)
        self._delta_buffer = _DeltaEventBuffer()

    @property
    def final_messages(self) -> list[dict[str, Any]]:
        """返回本次 Pydantic AI run 新增的消息历史。"""

        return self._final_messages

    async def handle_raw_event(self, raw_event: Any) -> list[AgentRunEvent]:
        """把单个 Pydantic AI 原始事件转换为零到多个平台事件。"""

        if isinstance(raw_event, AgentRunResultEvent):
            self._final_messages[:] = sanitize_message_history_image_refs(
                safe_new_messages(raw_event.result),
                image_refs=self._final_message_image_refs,
            )
            output = getattr(raw_event.result, "output", None)
            if isinstance(output, DeferredToolRequests):
                emitted = await self.flush_delta_buffer()
                if self._on_deferred is not None:
                    paused_event = await self._on_deferred(output, self._final_messages)
                    if paused_event is not None:
                        emitted.append(paused_event)
                return emitted
            return []
        if isinstance(raw_event, PartStartEvent):
            return await self._handle_part_start(raw_event.part)
        if isinstance(raw_event, PartDeltaEvent):
            return await self._handle_part_delta(raw_event.delta)
        if isinstance(raw_event, FunctionToolCallEvent):
            if _is_denied_tool_call(raw_event.part, self._denied_tool_call_ids):
                return []
            emitted = await self.flush_delta_buffer()
            emitted.append(await self._emit("tool.started", data=self._tool_payload(raw_event.part)))
            return emitted
        if isinstance(raw_event, FunctionToolResultEvent):
            emitted = await self.flush_delta_buffer()
            result = raw_event.result
            raw_tool_call_id = str(getattr(result, "tool_call_id", "") or "")
            if raw_tool_call_id in self._denied_tool_call_ids:
                emitted.append(
                    await self._emit(
                        "tool.error",
                        data={
                            "tool_name": getattr(result, "tool_name", None),
                            "tool_call_id": self._map_tool_call_id(raw_tool_call_id),
                            "message": _tool_denied_message(getattr(result, "content", None)),
                            **self._extra_tool_data(raw_tool_call_id),
                        },
                    )
                )
                return emitted
            emitted.append(
                await self._emit(
                    **self._tool_result_payload(
                        tool_name=getattr(result, "tool_name", None),
                        raw_tool_call_id=getattr(result, "tool_call_id", None),
                        content=getattr(result, "content", None),
                    )
                )
            )
            return emitted
        return []

    async def flush_delta_buffer(self, *, best_effort: bool = False) -> list[AgentRunEvent]:
        """强制写出当前 delta 缓冲；取消和异常路径可选择尽力而为。"""

        buffered = self._delta_buffer.pop()
        if buffered is None:
            return []
        try:
            return [await self._emit(buffered.event, content=buffered.content)]
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to flush buffered agent delta",
                extra={
                    "run_id": self._run_id,
                    "session_id": self._session_id,
                    "event": f"{self._event_prefix}{buffered.event}",
                },
            )
            if not best_effort:
                raise
            return []

    async def _handle_part_start(self, part: Any) -> list[AgentRunEvent]:
        """处理模型响应 part 开始事件。"""

        if isinstance(part, TextPart) and part.content:
            return await self._append_delta_event(event="message.delta", content=part.content)
        if isinstance(part, ThinkingPart) and part.content:
            return await self._append_delta_event(event="reasoning.delta", content=part.content)
        if isinstance(part, ToolCallPart):
            if _is_denied_tool_call(part, self._denied_tool_call_ids):
                return []
            emitted = await self.flush_delta_buffer()
            emitted.append(await self._emit("tool.started", data=self._tool_payload(part)))
            return emitted
        return []

    async def _handle_part_delta(self, delta: Any) -> list[AgentRunEvent]:
        """处理模型响应 part delta 事件。"""

        if isinstance(delta, TextPartDelta) and delta.content_delta:
            return await self._append_delta_event(event="message.delta", content=delta.content_delta)
        if isinstance(delta, ThinkingPartDelta) and delta.content_delta:
            return await self._append_delta_event(event="reasoning.delta", content=delta.content_delta)
        return []

    async def _append_delta_event(self, *, event: str, content: str) -> list[AgentRunEvent]:
        """追加模型文本 delta，并在达到阈值后写出合并事件。"""

        if event == "reasoning.delta":
            if self._on_reasoning_delta is not None:
                self._on_reasoning_delta(content)
        elif self._on_message_delta is not None:
            self._on_message_delta(content)
        emitted: list[AgentRunEvent] = []
        for buffered in self._delta_buffer.append(event=event, content=content):
            emitted.append(await self._emit(buffered.event, content=buffered.content))
        return emitted

    async def _emit(
        self,
        event: str,
        *,
        content: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> AgentRunEvent:
        """补齐命名空间、运行标识和固定数据后写入平台事件。"""

        event_data = {**self._base_event_data(), **(data or {})}
        return await self._append_event(
            AgentRunEvent(
                event=f"{self._event_prefix}{event}",
                run_id=self._run_id,
                session_id=self._session_id,
                content=content,
                data=event_data,
            )
        )

    def _tool_payload(self, part: ToolCallPart) -> dict[str, Any]:
        """把 Pydantic AI 工具调用片段转换为平台工具 payload。"""

        raw_tool_call_id = str(getattr(part, "tool_call_id", "") or "")
        return {
            "tool_name": part.tool_name,
            "tool_call_id": self._map_tool_call_id(raw_tool_call_id),
            "tool_args": part.args,
            **self._extra_tool_data(raw_tool_call_id),
        }

    def _tool_result_payload(self, *, tool_name: Any, raw_tool_call_id: Any, content: Any) -> dict[str, Any]:
        """把工具返回转换为 _emit 可直接使用的事件名和 data。"""

        raw_call_id = str(raw_tool_call_id or "")
        sanitized_content = sanitize_message_history_image_refs(content)
        data: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_call_id": self._map_tool_call_id(raw_call_id),
            **self._extra_tool_data(raw_call_id),
        }
        if is_recoverable_tool_error_result(content):
            return {
                "event": "tool.error",
                "data": {
                    **data,
                    "message": _recoverable_tool_error_message(content),
                    "result": sanitized_content,
                },
            }
        return {
            "event": "tool.completed",
            "data": {
                **data,
                "result": sanitized_content,
            },
        }


@dataclass(slots=True)
class _BufferedDelta:
    """描述一次准备落库的合并 delta。"""

    event: str
    content: str


class _DeltaEventBuffer:
    """按类型、时间和大小合并模型原始 delta。"""

    def __init__(self) -> None:
        """初始化空缓冲。"""

        self._event: str | None = None
        self._parts: list[str] = []
        self._byte_size = 0
        self._started_at: float | None = None

    def append(self, *, event: str, content: str) -> list[_BufferedDelta]:
        """追加 delta 内容，返回需要立即落库的缓冲片段。"""

        now = monotonic()
        flushed: list[_BufferedDelta] = []
        if self._event is not None and (self._event != event or self._should_flush_before_append(now)):
            buffered = self.pop()
            if buffered is not None:
                flushed.append(buffered)
        if self._event is None:
            self._event = event
            self._started_at = now
        self._parts.append(content)
        self._byte_size += len(content.encode("utf-8"))
        if self._byte_size >= _delta_flush_bytes(event):
            buffered = self.pop()
            if buffered is not None:
                flushed.append(buffered)
        return flushed

    def pop(self) -> _BufferedDelta | None:
        """弹出当前缓冲内容。"""

        if self._event is None or not self._parts:
            self._reset()
            return None
        buffered = _BufferedDelta(event=self._event, content="".join(self._parts))
        self._reset()
        return buffered

    def _should_flush_before_append(self, now: float) -> bool:
        """判断当前缓冲是否已经超过对应类型的时间阈值。"""

        if self._event is None or self._started_at is None:
            return False
        return now - self._started_at >= _delta_flush_interval_seconds(self._event)

    def _reset(self) -> None:
        """清空当前缓冲状态。"""

        self._event = None
        self._parts = []
        self._byte_size = 0
        self._started_at = None


def safe_messages(result: Any) -> list[dict[str, Any]]:
    """安全序列化 Pydantic AI result 历史消息。"""

    try:
        dumped = ModelMessagesTypeAdapter.dump_python(result.all_messages(), mode="json")
        return dumped if isinstance(dumped, list) else []
    except Exception:  # noqa: BLE001
        return []


def safe_new_messages(result: Any) -> list[dict[str, Any]]:
    """安全序列化本次 Pydantic AI run 新增消息，避免跨 run 重复持久化历史。"""

    try:
        new_messages = getattr(result, "new_messages", None)
        if not callable(new_messages):
            return []
        dumped = ModelMessagesTypeAdapter.dump_python(new_messages(), mode="json")
        return dumped if isinstance(dumped, list) else []
    except Exception:  # noqa: BLE001
        return []


def denied_tool_call_ids(results: DeferredToolResults | None) -> set[str]:
    """从 deferred approval 结果中提取被人工拒绝的 tool_call_id。"""

    if results is None:
        return set()
    return {
        str(tool_call_id)
        for tool_call_id, approval_result in results.approvals.items()
        if isinstance(approval_result, ToolDenied) and str(tool_call_id).strip()
    }


def _is_denied_tool_call(part: ToolCallPart, denied_tool_call_ids: set[str]) -> bool:
    """判断工具调用是否属于拒绝回灌，避免把平台错误态覆盖为运行中。"""

    tool_call_id = str(getattr(part, "tool_call_id", "") or "")
    return bool(tool_call_id and tool_call_id in denied_tool_call_ids)


def _delta_flush_interval_seconds(event: str) -> float:
    """返回指定 delta 事件的时间 flush 阈值。"""

    if event == "reasoning.delta":
        return _REASONING_DELTA_FLUSH_INTERVAL_SECONDS
    return _MESSAGE_DELTA_FLUSH_INTERVAL_SECONDS


def _delta_flush_bytes(event: str) -> int:
    """返回指定 delta 事件的大小 flush 阈值。"""

    if event == "reasoning.delta":
        return _REASONING_DELTA_FLUSH_BYTES
    return _MESSAGE_DELTA_FLUSH_BYTES


def _tool_denied_message(content: Any) -> str:
    """把 Pydantic AI 的拒绝回灌内容转换为前端可展示消息。"""

    text = str(content or "").strip()
    return text or "用户拒绝执行该工具。"


def _recoverable_tool_error_message(content: Any) -> str:
    """提取可恢复工具错误的展示文案。"""

    if not isinstance(content, dict):
        return "工具调用失败。"
    error = content.get("error")
    if not isinstance(error, dict):
        return "工具调用失败。"
    message = str(error.get("message") or "").strip()
    code = str(error.get("code") or "").strip()
    if code and message:
        return f"{code} {message}"
    return message or code or "工具调用失败。"
