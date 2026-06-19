"""文件功能：定义 Agent 会话 Facade 的流式运行跟踪模型与临时历史缓冲。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections.abc import AsyncIterator

from agno.run.base import RunStatus

from app.ai.session_facade_common import (
    _coerce_str,
    _extract_text_content,
    _normalize_raw_event_payload,
    _raw_event_name,
    _resolve_reasoning_content,
    _split_reasoning_content,
)
from app.schemas.agent import AgentRunEvent


_ACTIVE_RUN_STATUSES = {RunStatus.pending, RunStatus.running, RunStatus.paused}
_TERMINAL_RUN_EVENTS = {"run.completed", "run.cancelled", "run.error", "run.paused"}


@dataclass(slots=True)
class _ActiveAgentStream:
    """保存一次运行对应的 Agent 实例与事件流，便于后续注册取消句柄。"""

    agent: Any
    stream: AsyncIterator[Any]
    run_id: str | None = None


@dataclass(slots=True)
class _SessionMessageRecord:
    """记录 Agno 消息及其所属 run，用于 Editor 恢复附件与工具锚点。"""

    run_id: str | None
    message: Any


@dataclass(slots=True)
class _TempHistoryMessage:
    """保存当前 run 中尚未写入 Agno session 的临时历史消息。"""

    role: str
    content: Any
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: Any | None = None
    tool_call_error: str | None = None



class _StreamingHistoryTracker:
    """累计当前 run 内已稳定完成的消息，用于中途刷新上下文统计。"""

    def __init__(self, initial_messages: list[Any] | None = None) -> None:
        self._messages: list[Any] = list(initial_messages or [])
        self._assistant_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._last_assistant_content = ""
        self._last_reasoning_content = ""
        self._tool_args_by_call_id: dict[str, Any] = {}

    def snapshot(self) -> list[Any]:
        """返回临时历史消息副本，避免估算过程修改内部缓冲。"""

        return [*self._messages]

    @property
    def fallback_user_content(self) -> str | None:
        """返回本轮用户输入兜底文本，用于取消时补偿历史。"""

        for message in self._messages:
            if str(getattr(message, "role", "") or "") != "user":
                continue
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
        return None

    @property
    def assistant_content(self) -> str | None:
        """返回本轮已稳定或仍在缓冲中的 assistant 正文。"""

        content = "".join(self._assistant_parts) or self._last_assistant_content
        return content or None

    @property
    def reasoning_content(self) -> str | None:
        """返回本轮已稳定或仍在缓冲中的 reasoning 内容。"""

        content = "".join(self._reasoning_parts) or self._last_reasoning_content
        return content or None

    @property
    def has_preservable_content(self) -> bool:
        """判断当前 tracker 是否有可写入取消历史的内容。"""

        return bool(self.fallback_user_content or self.assistant_content or self.reasoning_content)

    def append_assistant_delta(self, content: str | None, reasoning_content: str | None = None) -> None:
        """累计流式 assistant 文本片段，等内容完成检查点再落入临时历史。"""

        if content:
            self._assistant_parts.append(content)
        if reasoning_content:
            self._reasoning_parts.append(reasoning_content)

    def flush_assistant_content(self, fallback_content: str | None = None) -> bool:
        """把当前 assistant 文本缓冲固化为一条临时历史消息。"""

        content = "".join(self._assistant_parts)
        reasoning_content = "".join(self._reasoning_parts)
        self._assistant_parts = []
        self._reasoning_parts = []
        if not content and fallback_content:
            content = fallback_content
        if reasoning_content:
            self._last_reasoning_content = reasoning_content
        if not content or content == self._last_assistant_content:
            return False
        self._messages.append(_TempHistoryMessage(role="assistant", content=content))
        self._last_assistant_content = content
        return True

    def remember_tool_started(self, event: AgentRunEvent) -> None:
        """记录工具入参，供完成或失败检查点估算工具消息。"""

        tool_call_id = _coerce_str(event.data.get("tool_call_id"))
        if not tool_call_id:
            return
        self._tool_args_by_call_id[tool_call_id] = event.data.get("tool_args")

    def append_tool_event(self, event: AgentRunEvent) -> bool:
        """把工具完成或失败结果固化为一条临时工具消息。"""

        tool_name = _coerce_str(event.data.get("tool_name"))
        tool_call_id = _coerce_str(event.data.get("tool_call_id"))
        result = event.data.get("result")
        message = event.data.get("message")
        content = result if result is not None else message
        if content is None:
            content = ""
        self._messages.append(
            _TempHistoryMessage(
                role="tool",
                content=content,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_args=self._tool_args_by_call_id.get(tool_call_id or ""),
                tool_call_error=_coerce_str(message) if event.event == "tool.error" else None,
            )
        )
        return True


@dataclass(slots=True)

class _RawSseRunMessageTracker:
    """跟踪 Agno raw SSE 中已展示给用户的当前 run 内容。"""

    fallback_user_message: str | None = None
    run_id: str | None = None
    cancelled: bool = False
    terminal_status: RunStatus | None = None
    assistant_parts: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)

    def observe(self, raw_event: Any, *, fallback_run_id: str | None = None) -> None:
        """读取 raw Agno 事件中的 run、正文、reasoning 和取消终态。"""

        payload = _normalize_raw_event_payload(raw_event)
        event_name = _raw_event_name(raw_event, payload)
        self.observe_payload(payload, event_name=event_name, fallback_run_id=fallback_run_id)

    def observe_payload(
        self,
        payload: dict[str, Any],
        *,
        event_name: str,
        fallback_run_id: str | None = None,
    ) -> None:
        """读取已解析的 raw payload，统一识别 run、输出片段和终态。"""

        event_run_id = _coerce_str(payload.get("run_id")) or fallback_run_id
        if event_run_id:
            self.run_id = event_run_id
        if event_name in {
            "RunContent",
            "RunContentEvent",
            "IntermediateRunContent",
            "IntermediateRunContentEvent",
            "RunIntermediateContent",
            "TeamRunContent",
            "TeamRunIntermediateContent",
        }:
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload, preserve_stream_boundary=True),
                preserve_reasoning_boundary=True,
            )
            if content:
                self.assistant_parts.append(content)
            if reasoning_content:
                self.reasoning_parts.append(reasoning_content)
        elif event_name == "ReasoningContentDelta":
            reasoning_content = _resolve_reasoning_content(payload, preserve_stream_boundary=True)
            if reasoning_content:
                self.reasoning_parts.append(reasoning_content)
        elif event_name in {"RunCompleted", "RunCompletedEvent", "TeamRunCompleted"}:
            self.terminal_status = RunStatus.completed
            content, reasoning_content = _split_reasoning_content(
                _extract_text_content(payload.get("content")),
                _resolve_reasoning_content(payload, preserve_stream_boundary=True),
                preserve_reasoning_boundary=True,
            )
            if content and not "".join(self.assistant_parts):
                self.assistant_parts.append(content)
            if reasoning_content and not "".join(self.reasoning_parts):
                self.reasoning_parts.append(reasoning_content)
        elif event_name in {"RunCancelled", "RunCancelledEvent", "TeamRunCancelled"}:
            self.cancelled = True
            self.terminal_status = RunStatus.cancelled
        elif event_name in {"RunError", "RunErrorEvent", "TeamRunError"}:
            self.terminal_status = RunStatus.error
        elif event_name in {"RunPaused", "RunPausedEvent", "TeamRunPaused"}:
            self.terminal_status = RunStatus.paused

    @property
    def assistant_content(self) -> str | None:
        """返回当前 run 已流出的 assistant 正文。"""

        content = "".join(self.assistant_parts or [])
        return content or None

    @property
    def reasoning_content(self) -> str | None:
        """返回当前 run 已流出的 reasoning 内容。"""

        content = "".join(self.reasoning_parts or [])
        return content or None

