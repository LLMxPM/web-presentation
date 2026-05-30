"""文件功能：从 Agno run 的 events/messages 重建 Editor 可渲染的运行时 timeline。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from agno.run.base import RunStatus
from fastapi.encoders import jsonable_encoder

from app.ai.agent import AgentRuntimeContext
from app.schemas.agent import AgentPendingRequirement, AgentTimelineItem, AgentTimelineToolItem

_REASONING_BLOCK_PATTERN = re.compile(r"<reasoning>(.*?)</reasoning>", re.IGNORECASE | re.DOTALL)
_THINK_BLOCK_PATTERN = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
_OPEN_REASONING_TAG_PATTERN = re.compile(r"<(?:reasoning|think)>", re.IGNORECASE)
_REASONING_TAG_PATTERN = re.compile(r"</?(?:reasoning|think)>", re.IGNORECASE)
_AGNO_CONTEXT_NOTE_PREFIX = "Take note of the following content"

ExtractRequirement = Callable[..., AgentPendingRequirement | None]
RequirementTextBuilder = Callable[[AgentPendingRequirement], str]


@dataclass(slots=True)
class _AnsweredAskUserMessage:
    """记录已回答 ask_user 的 Agno tool message，供暂停事件回锚。"""

    message_index: int
    tool_call_id: str | None
    input_payload: Any
    output_payload: Any
    questions: list[str]
    message: str
    created_at: str | None


@dataclass(slots=True)
class _MatchedToolEvent:
    """保存一个 event 派生工具项及其 message 匹配元数据。"""

    sort_key: tuple[float, float]
    item: AgentTimelineItem
    has_result: bool


def build_timeline_items_from_agno_runs(
    detail: Any,
    *,
    session_id: str,
    agent_id: str,
    runtime_context: AgentRuntimeContext | None = None,
    target_run_ids: set[str] | None = None,
    include_child_runs: bool = False,
    hide_member_events: bool = True,
    extract_pending_requirement: ExtractRequirement | None = None,
    pending_requirement_timeline_content: RequirementTextBuilder | None = None,
) -> list[AgentTimelineItem]:
    """从 Agno runs/messages/events 派生 session-first 时间线。"""

    items: list[AgentTimelineItem] = []
    order_index = 0
    sort_keys_by_id: dict[str, tuple[float, float, float]] = {}

    def append_item(
        *,
        item_id: str,
        run_id: str,
        kind: str,
        role: str | None = None,
        event_index: int | None = None,
        content: str | None = None,
        status: str | None = None,
        tool: AgentTimelineToolItem | None = None,
        source: str = "synthetic",
        created_at: str | None = None,
        sort_key: tuple[float, float] | None = None,
    ) -> AgentTimelineItem:
        """追加时间线项，并记录稳定排序键。"""

        nonlocal order_index
        sequence = order_index
        item = AgentTimelineItem(
            id=item_id,
            session_id=session_id,
            run_id=run_id,
            kind=kind,  # type: ignore[arg-type]
            role=role,  # type: ignore[arg-type]
            event_index=event_index,
            order_index=sequence,
            content=content,
            status=status,
            tool=tool,
            source=source,  # type: ignore[arg-type]
            created_at=created_at,
        )
        order_index += 1
        resolved_sort_key = sort_key or (float(sequence), 0.0)
        sort_keys_by_id[item.id] = (resolved_sort_key[0], resolved_sort_key[1], float(sequence))
        items.append(item)
        return item

    for run_index, run in enumerate(getattr(detail, "runs", None) or []):
        run_id = _coerce_str(getattr(run, "run_id", None)) or f"run-{run_index}"
        if target_run_ids is not None and run_id not in target_run_ids:
            continue
        owner_id = _resolve_run_owner_id(run)
        if target_run_ids is None and owner_id is not None and str(owner_id) != agent_id:
            continue
        if not include_child_runs and getattr(run, "parent_run_id", None) is not None:
            continue

        run_sort_base = float(run_index * 1_000_000_000)
        run_created_at = _normalize_timestamp(getattr(run, "created_at", None))

        def user_message_sort_key(message_index: int) -> tuple[float, float]:
            """用户输入固定排在当前 run 事件轴之前。"""

            return (run_sort_base + float(message_index), 0.0)

        def event_sort_key(event_index: int, slot: float = 0.0) -> tuple[float, float]:
            """事件使用 Agno run.events 列表下标作为主排序轴。"""

            return (run_sort_base + 10_000.0 + float(event_index * 10) + slot, 0.0)

        def message_fallback_sort_key(message_index: int, slot: float = 0.0) -> tuple[float, float]:
            """没有事件锚点的 message fallback 保留 Agno messages 自身顺序。"""

            return (run_sort_base + 500_000_000.0 + float(message_index * 10) + slot, 0.0)

        def run_tail_sort_key(slot: float = 0.0) -> tuple[float, float]:
            """requirement/status 等运行尾部合成项排在当前 run 末尾。"""

            return (run_sort_base + 900_000_000.0 + slot, 0.0)

        displayable_messages = [
            message
            for message in list(getattr(run, "messages", None) or [])
            if _is_displayable_session_message(message)
        ]
        ask_user_answers_by_call_id, ask_user_answers_by_question = _index_answered_ask_user_messages(displayable_messages)
        consumed_ask_user_answer_message_indexes: set[int] = set()
        user_messages = [
            (message_index, message)
            for message_index, message in enumerate(displayable_messages)
            if str(_message_attr(message, "role", "") or "") == "user"
        ]
        if user_messages:
            for original_message_index, message in user_messages:
                content, _ = _split_reasoning_content(
                    _stringify_content(_message_attr(message, "content", None)),
                    _resolve_reasoning_content(message),
                )
                append_item(
                    item_id=f"{session_id}:{run_id}:message:user:{original_message_index}",
                    run_id=run_id,
                    kind="message",
                    role="user",
                    content=content,
                    source="message",
                    created_at=_normalize_timestamp(_message_attr(message, "created_at", None)) or run_created_at,
                    sort_key=user_message_sort_key(original_message_index),
                )
        else:
            user_input = _resolve_run_input_text(run)
            if user_input:
                append_item(
                    item_id=f"{session_id}:{run_id}:input:user",
                    run_id=run_id,
                    kind="message",
                    role="user",
                    content=user_input,
                    source="synthetic",
                    created_at=run_created_at,
                    sort_key=user_message_sort_key(0),
                )

        current_text_item: AgentTimelineItem | None = None
        current_text_kind: str | None = None
        assistant_text_since_boundary = ""
        reasoning_text_since_boundary = ""
        event_text_items: list[AgentTimelineItem] = []
        event_tool_matches_by_key: dict[tuple[str | None, str], list[_MatchedToolEvent]] = {}
        event_tool_matches_by_call_id: dict[str, list[_MatchedToolEvent]] = {}
        event_tool_match_by_detail_id: dict[str, _MatchedToolEvent] = {}
        event_tool_positions: list[float] = []
        detail_by_id: dict[str, AgentTimelineItem] = {}
        pending_without_call_id: dict[tuple[str, str], str] = {}
        requirement_from_events = False

        def close_text_segment(*, reset_boundary: bool) -> None:
            """关闭当前流式文本片段；工具和 requirement 会形成新的语义边界。"""

            nonlocal current_text_item, current_text_kind, assistant_text_since_boundary, reasoning_text_since_boundary
            current_text_item = None
            current_text_kind = None
            if reset_boundary:
                assistant_text_since_boundary = ""
                reasoning_text_since_boundary = ""

        def append_event_text(
            *,
            kind: str,
            content: str,
            event_index: int,
            created_at: str | None,
            sort_key: tuple[float, float],
        ) -> AgentTimelineItem:
            """按前端流式规则追加 reasoning 或 assistant 文本片段。"""

            nonlocal current_text_item, current_text_kind, assistant_text_since_boundary, reasoning_text_since_boundary
            if current_text_item is not None and current_text_kind == kind:
                current_text_item.content = f"{current_text_item.content or ''}{content}"
                item = current_text_item
            else:
                item = append_item(
                    item_id=f"{session_id}:{run_id}:event:{event_index}:{kind}",
                    run_id=run_id,
                    kind="message" if kind == "assistant" else "reasoning",
                    role="assistant" if kind == "assistant" else None,
                    event_index=event_index,
                    content=content,
                    source="event",
                    created_at=created_at,
                    sort_key=sort_key,
                )
                current_text_item = item
                current_text_kind = kind
                event_text_items.append(item)
            if kind == "assistant":
                assistant_text_since_boundary = f"{assistant_text_since_boundary}{content}"
            else:
                reasoning_text_since_boundary = f"{reasoning_text_since_boundary}{content}"
            return item

        def same_sort_window(left_key: tuple[float, float], right_key: tuple[float, float]) -> bool:
            """判断两个文本项是否位于同一组相邻工具事件之间。"""

            def window_for(sort_key: tuple[float, float]) -> tuple[float | None, float | None]:
                position = sort_key[0]
                previous = [item for item in event_tool_positions if item < position]
                next_items = [item for item in event_tool_positions if item > position]
                return (max(previous) if previous else None, min(next_items) if next_items else None)

            return window_for(left_key) == window_for(right_key)

        def merge_or_skip_existing_text(
            *,
            kind: str,
            content: str | None,
            sort_key: tuple[float, float],
        ) -> bool:
            """用 message 补强同窗口 event 文本；完全重复时直接跳过。"""

            incoming_text = _normalize_compare_text(content)
            if not incoming_text:
                return True
            for event_item in event_text_items:
                if kind == "assistant" and not (event_item.kind == "message" and event_item.role == "assistant"):
                    continue
                if kind == "reasoning" and event_item.kind != "reasoning":
                    continue
                event_item_sort_key = sort_keys_by_id.get(event_item.id, (float(event_item.order_index), 0.0, 0.0))
                if not same_sort_window((event_item_sort_key[0], event_item_sort_key[1]), sort_key):
                    continue
                existing_text = _normalize_compare_text(event_item.content)
                if not existing_text:
                    continue
                if existing_text == incoming_text or incoming_text in existing_text:
                    return True
                if existing_text in incoming_text:
                    event_item.content = content
                    return True
            return False

        for event_index, raw_event in enumerate(getattr(run, "events", None) or []):
            payload = _event_payload(raw_event)
            if not isinstance(payload, dict):
                continue
            event_name = _raw_event_name(raw_event, payload)
            member_event_data = _extract_member_event_data(payload)
            if (
                hide_member_events
                and member_event_data.get("parent_run_id")
                and member_event_data.get("member_run_id")
            ):
                continue

            status = _tool_status_from_agno_event(event_name)
            if status is not None:
                close_text_segment(reset_boundary=True)
                tool_payload = payload.get("tool") if isinstance(payload.get("tool"), dict) else {}
                tool_name = _coerce_str(tool_payload.get("tool_name")) or "工具调用"
                tool_call_id = _coerce_str(tool_payload.get("tool_call_id"))
                detail_id = _resolve_tool_detail_id_for_agno(
                    run_id=run_id,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    event_name=event_name,
                    event_index=event_index,
                    pending_without_call_id=pending_without_call_id,
                )
                existing = detail_by_id.get(detail_id)
                existing_tool = existing.tool if existing is not None else None
                result_present = "result" in tool_payload and tool_payload.get("result") is not None
                result = tool_payload.get("result") if result_present else payload.get("content")
                input_payload = tool_payload.get("tool_args") if "tool_args" in tool_payload else None
                if input_payload is None and existing_tool is not None:
                    input_payload = existing_tool.input_payload
                message = _stringify_content(
                    payload.get("content")
                    or tool_payload.get("error")
                    or (existing_tool.message if existing_tool is not None else "")
                )
                tool_item = AgentTimelineToolItem(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    member_agent_id=_coerce_str(member_event_data.get("member_agent_id"))
                    or (existing_tool.member_agent_id if existing_tool is not None else None),
                    member_agent_name=_coerce_str(member_event_data.get("member_agent_name"))
                    or (existing_tool.member_agent_name if existing_tool is not None else None),
                    member_run_id=_coerce_str(member_event_data.get("member_run_id"))
                    or (existing_tool.member_run_id if existing_tool is not None else None),
                    status=status,  # type: ignore[arg-type]
                    input_payload=_safe_json_payload(input_payload),
                    output_payload=_safe_json_payload(result)
                    if result is not None
                    else (existing_tool.output_payload if existing_tool is not None else None),
                    message=message,
                )
                tool_sort_key = event_sort_key(event_index)
                if existing is not None:
                    existing.tool = tool_item
                    existing.status = status
                    if existing.created_at is None:
                        existing.created_at = _normalize_timestamp(payload.get("created_at"))
                    matched_tool = event_tool_match_by_detail_id.get(detail_id)
                    if matched_tool is not None:
                        matched_tool.has_result = matched_tool.has_result or result_present
                else:
                    existing = append_item(
                        item_id=f"{session_id}:{detail_id}",
                        run_id=run_id,
                        kind="tool",
                        event_index=event_index,
                        status=status,
                        tool=tool_item,
                        source="event",
                        created_at=_normalize_timestamp(payload.get("created_at")) or run_created_at,
                        sort_key=tool_sort_key,
                    )
                    detail_by_id[detail_id] = existing
                    matched_tool = _MatchedToolEvent(sort_key=tool_sort_key, item=existing, has_result=result_present)
                    event_tool_match_by_detail_id[detail_id] = matched_tool
                    event_tool_matches_by_key.setdefault((tool_call_id, tool_name), []).append(matched_tool)
                    if tool_call_id:
                        event_tool_matches_by_call_id.setdefault(tool_call_id, []).append(matched_tool)
                    event_tool_positions.append(tool_sort_key[0])
                    event_tool_positions.sort()
                continue

            if event_name in {"RunPaused", "RunPausedEvent", "TeamRunPaused"}:
                close_text_segment(reset_boundary=True)
                requirement = _call_extract_pending_requirement(
                    extract_pending_requirement,
                    payload={**payload, "session_id": session_id, "run_id": run_id},
                    runtime_context=runtime_context,
                )
                if requirement is not None:
                    answered_message = _pop_answered_ask_user_message(
                        requirement,
                        by_call_id=ask_user_answers_by_call_id,
                        by_question=ask_user_answers_by_question,
                    )
                    if answered_message is not None:
                        consumed_ask_user_answer_message_indexes.add(answered_message.message_index)
                        append_item(
                            item_id=f"{session_id}:{run_id}:ask-user:{answered_message.tool_call_id or event_index}",
                            run_id=run_id,
                            kind="tool",
                            event_index=event_index,
                            status="completed",
                            tool=AgentTimelineToolItem(
                                tool_call_id=answered_message.tool_call_id,
                                tool_name="ask_user",
                                status="completed",
                                input_payload=answered_message.input_payload,
                                output_payload=answered_message.output_payload,
                                message=answered_message.message,
                            ),
                            source="message",
                            created_at=answered_message.created_at
                            or _normalize_timestamp(payload.get("created_at"))
                            or run_created_at,
                            sort_key=event_sort_key(event_index, 5.0),
                        )
                    else:
                        requirement_from_events = True
                        append_item(
                            item_id=f"{session_id}:{run_id}:event:{event_index}:requirement:{requirement.id or requirement.tool_name or 'pending'}",
                            run_id=run_id,
                            kind="requirement",
                            event_index=event_index,
                            status="pending",
                            content=_call_requirement_timeline_content(
                                pending_requirement_timeline_content,
                                requirement,
                            ),
                            source="event",
                            created_at=_normalize_timestamp(payload.get("created_at")) or run_created_at,
                            sort_key=event_sort_key(event_index, 5.0),
                        )
                continue

            content, reasoning_content = _timeline_content_from_event(
                event_name=event_name,
                payload=payload,
                hide_member_events=hide_member_events,
            )
            if _is_timeline_completed_event(event_name):
                if assistant_text_since_boundary or _is_structured_text_payload(content):
                    content = None
                if reasoning_text_since_boundary:
                    reasoning_content = None
            created_at = _normalize_timestamp(payload.get("created_at")) or run_created_at
            if reasoning_content:
                append_event_text(
                    kind="reasoning",
                    content=reasoning_content,
                    event_index=event_index,
                    created_at=created_at,
                    sort_key=event_sort_key(event_index, 1.0),
                )
            if content:
                append_event_text(
                    kind="assistant",
                    content=content,
                    event_index=event_index,
                    created_at=created_at,
                    sort_key=event_sort_key(event_index, 2.0),
                )

        tool_message_event_matches_by_index: dict[int, _MatchedToolEvent] = {}
        used_event_tool_item_ids: set[str] = set()
        for message_index, message in enumerate(displayable_messages):
            if str(_message_attr(message, "role", "") or "") != "tool":
                continue
            if message_index in consumed_ask_user_answer_message_indexes:
                continue
            tool_name = _coerce_str(_message_attr(message, "tool_name", None)) or "工具调用"
            tool_call_id = _coerce_str(_message_attr(message, "tool_call_id", None))
            key = (tool_call_id, tool_name)
            candidates = [
                candidate
                for candidate in event_tool_matches_by_key.get(key) or []
                if candidate.item.id not in used_event_tool_item_ids
            ]
            matched_tool: _MatchedToolEvent | None = None
            if candidates:
                matched_tool = candidates[0]
            elif tool_call_id:
                call_id_candidates = [
                    candidate
                    for candidate in event_tool_matches_by_call_id.get(tool_call_id) or []
                    if candidate.item.id not in used_event_tool_item_ids
                ]
                if call_id_candidates:
                    matched_tool = call_id_candidates[0]
            if matched_tool is not None:
                used_event_tool_item_ids.add(matched_tool.item.id)
                tool_message_event_matches_by_index[message_index] = matched_tool
                _merge_tool_message_into_event_item(matched_tool=matched_tool, message=message)

        def assistant_message_sort_key(message_index: int) -> tuple[float, float]:
            """把 assistant fallback 锚到相邻 tool 事件之间，避免刷新后按类型分桶。"""

            previous_tool_key: tuple[float, float] | None = None
            next_tool_key: tuple[float, float] | None = None
            for previous_index in range(message_index - 1, -1, -1):
                previous_tool = tool_message_event_matches_by_index.get(previous_index)
                previous_tool_key = previous_tool.sort_key if previous_tool is not None else None
                if previous_tool_key is not None:
                    break
            for next_index in range(message_index + 1, len(displayable_messages)):
                next_tool = tool_message_event_matches_by_index.get(next_index)
                next_tool_key = next_tool.sort_key if next_tool is not None else None
                if next_tool_key is not None:
                    break
            offset = float(message_index) / 1_000_000.0
            if previous_tool_key is not None and next_tool_key is not None:
                return (((previous_tool_key[0] + next_tool_key[0]) / 2.0) + offset, 0.0)
            if previous_tool_key is not None:
                return (previous_tool_key[0] + 5.0 + offset, 0.0)
            if next_tool_key is not None:
                return (next_tool_key[0] - 5.0 + offset, 0.0)
            return message_fallback_sort_key(message_index)

        for message_index, message in enumerate(displayable_messages):
            if str(_message_attr(message, "role", "") or "") != "assistant":
                continue
            content, reasoning_content = _split_reasoning_content(
                _stringify_content(_message_attr(message, "content", None)),
                _resolve_reasoning_content(message),
            )
            created_at = _normalize_timestamp(_message_attr(message, "created_at", None)) or run_created_at
            assistant_sort_key = assistant_message_sort_key(message_index)
            if reasoning_content and not merge_or_skip_existing_text(
                kind="reasoning",
                content=reasoning_content,
                sort_key=(assistant_sort_key[0] - 0.2, 0.0),
            ):
                append_item(
                    item_id=f"{session_id}:{run_id}:message:assistant:{message_index}:reasoning",
                    run_id=run_id,
                    kind="reasoning",
                    content=reasoning_content,
                    source="message",
                    created_at=created_at,
                    sort_key=(assistant_sort_key[0] - 0.2, 0.0),
                )
            if content and not _is_structured_text_payload(content) and not merge_or_skip_existing_text(
                kind="assistant",
                content=content,
                sort_key=assistant_sort_key,
            ):
                append_item(
                    item_id=f"{session_id}:{run_id}:message:assistant:{message_index}",
                    run_id=run_id,
                    kind="message",
                    role="assistant",
                    content=content,
                    source="message",
                    created_at=created_at,
                    sort_key=assistant_sort_key,
                )

        for message_index, message in enumerate(displayable_messages):
            if str(_message_attr(message, "role", "") or "") != "tool":
                continue
            if message_index in consumed_ask_user_answer_message_indexes:
                continue
            if message_index in tool_message_event_matches_by_index:
                continue
            tool_name = _coerce_str(_message_attr(message, "tool_name", None)) or "工具调用"
            tool_call_id = _coerce_str(_message_attr(message, "tool_call_id", None))
            tool_error = _message_tool_error_text(message)
            tool_item = AgentTimelineToolItem(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="error" if tool_error else "completed",
                input_payload=_safe_json_payload(_message_attr(message, "tool_args", None)),
                output_payload=_message_tool_output_payload(message),
                message=tool_error or "",
            )
            append_item(
                item_id=f"{session_id}:{run_id}:message:tool:{message_index}",
                run_id=run_id,
                kind="tool",
                status=tool_item.status,
                tool=tool_item,
                source="message",
                created_at=_normalize_timestamp(_message_attr(message, "created_at", None)) or run_created_at,
                sort_key=message_fallback_sort_key(message_index),
            )

        requirement = None
        if not requirement_from_events:
            requirement = _call_extract_pending_requirement(
                extract_pending_requirement,
                payload={**_active_run_payload(run), "session_id": session_id, "run_id": run_id},
                runtime_context=runtime_context,
            )
        if requirement is not None:
            append_item(
                item_id=f"{session_id}:{run_id}:requirement:{requirement.id or requirement.tool_name or 'pending'}",
                run_id=run_id,
                kind="requirement",
                status="pending",
                content=_call_requirement_timeline_content(pending_requirement_timeline_content, requirement),
                source="synthetic",
                created_at=_normalize_timestamp(getattr(run, "updated_at", None)) or run_created_at,
                sort_key=run_tail_sort_key(0.0),
            )

        run_status = _normalize_run_status_value(getattr(run, "status", None))
        if run_status in {"paused", "cancelled", "failed", "completed"}:
            latest_event_index = _run_latest_event_index(run)
            append_item(
                item_id=f"{session_id}:{run_id}:status:{run_status}",
                run_id=run_id,
                kind="run_status",
                event_index=latest_event_index if latest_event_index >= 0 else None,
                content=_timeline_run_status_content(run_status, getattr(run, "content", None)),
                status=run_status,
                source="synthetic",
                created_at=_normalize_timestamp(getattr(run, "updated_at", None)) or run_created_at,
                sort_key=run_tail_sort_key(10.0),
            )

    items.sort(key=lambda item: sort_keys_by_id.get(item.id, (float(item.order_index), 0.0, float(item.order_index))))
    for item_index, item in enumerate(items):
        item.order_index = item_index
    return items


def _call_extract_pending_requirement(
    callback: ExtractRequirement | None,
    *,
    payload: dict[str, Any],
    runtime_context: AgentRuntimeContext | None,
) -> AgentPendingRequirement | None:
    """调用 facade 传入的 requirement 解析器，缺失时安全返回空。"""

    if callback is None:
        return None
    return callback(payload=payload, runtime_context=runtime_context)


def _call_requirement_timeline_content(
    callback: RequirementTextBuilder | None,
    requirement: AgentPendingRequirement,
) -> str:
    """调用 facade 传入的 requirement 文案生成器，缺失时使用兜底文案。"""

    if callback is None:
        return requirement.note or requirement.tool_name or "等待用户处理。"
    return callback(requirement)


def _merge_tool_message_into_event_item(*, matched_tool: _MatchedToolEvent, message: Any) -> None:
    """把 Agno tool message 中更完整的入参与结果合并回 event 派生工具项。"""

    item = matched_tool.item
    tool = item.tool
    if tool is None:
        return

    message_input_payload = _message_attr(message, "tool_args", None)
    if tool.input_payload is None and message_input_payload is not None:
        tool.input_payload = _safe_json_payload(message_input_payload)

    message_output_payload = _message_tool_output_payload(message)
    if _should_prefer_message_tool_output(
        matched_tool=matched_tool,
        event_output_payload=tool.output_payload,
        event_message=tool.message,
        message_output_payload=message_output_payload,
    ):
        tool.output_payload = message_output_payload

    tool_error = _message_tool_error_text(message)
    if tool_error:
        tool.status = "error"
        tool.message = tool_error
        item.status = "error"


def _should_prefer_message_tool_output(
    *,
    matched_tool: _MatchedToolEvent,
    event_output_payload: Any,
    event_message: str,
    message_output_payload: Any,
) -> bool:
    """判断 tool message 是否比工具事件更适合作为最终输出。"""

    if message_output_payload is None:
        return False
    if event_output_payload is None:
        return True
    if not matched_tool.has_result:
        return True
    if isinstance(event_output_payload, str) and not isinstance(message_output_payload, str):
        return True
    if event_message and _normalize_compare_text(event_output_payload) == _normalize_compare_text(event_message):
        return True
    return False


def _message_tool_output_payload(message: Any) -> Any:
    """读取工具消息输出，优先把 JSON 字符串还原为结构化载荷。"""

    content = _message_attr(message, "content", None)
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return _safe_json_payload(json.loads(stripped))
            except json.JSONDecodeError:
                pass
    return _safe_json_payload(content)


def _message_tool_error_text(message: Any) -> str | None:
    """读取真实工具错误文本，避免把布尔 False 当成错误消息。"""

    raw_error = _message_attr(message, "tool_call_error", None)
    if raw_error is None or raw_error is False:
        return None
    if raw_error is True:
        return _coerce_str(_message_attr(message, "content", None)) or "工具调用失败。"
    return _coerce_str(raw_error)


def _normalize_compare_text(value: Any) -> str:
    """把文本或 JSON 载荷规范化，供去重和包含判断使用。"""

    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return re.sub(r"\s+", " ", json.dumps(_safe_json_payload(value), ensure_ascii=False, sort_keys=True)).strip()


def _is_structured_text_payload(content: str | None) -> bool:
    """识别不应直接渲染成 assistant 正文的结构化 JSON 文本。"""

    if not isinstance(content, str):
        return False
    stripped = content.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return True


def _message_attr(message: Any, field_name: str, default: Any = None) -> Any:
    """兼容 Agno Message 对象和 dict 测试替身读取字段。"""

    if isinstance(message, dict):
        return message.get(field_name, default)
    return getattr(message, field_name, default)


def _is_displayable_session_message(message: Any, *, role: str | None = None) -> bool:
    """判断消息是否属于用户可见对话，过滤 Agno 历史和框架上下文注入。"""

    resolved_role = role or str(_message_attr(message, "role", "") or "")
    if resolved_role == "system":
        return False
    if resolved_role not in {"user", "assistant", "tool"}:
        return False
    if bool(_message_attr(message, "from_history", False)):
        return False
    if _is_agno_context_note_message(message, role=resolved_role):
        return False
    return True


def _is_agno_context_note_message(message: Any, *, role: str) -> bool:
    """识别 Agno 为图片或上下文附加的非用户输入提示消息。"""

    if role != "user":
        return False
    content = _stringify_content(_message_attr(message, "content", None)).strip()
    if not content.startswith(_AGNO_CONTEXT_NOTE_PREFIX):
        return False
    for field_name in ("images", "videos", "audio", "files"):
        if _message_attr(message, field_name, None):
            return True
    return False


def _coerce_str(value: Any) -> str | None:
    """把 metadata 中的展示字段安全转为非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_timestamp(value: Any) -> str | None:
    """把 Agno 时间字段统一转换为 ISO 字符串。"""

    if value is None or value == "":
        return None
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    if isinstance(value, float):
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _stringify_content(value: Any) -> str:
    """把 Agno 内容字段统一序列化为文本。"""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _safe_json_payload(value: Any) -> Any:
    """把 Agno/Pydantic 对象转为 JSON 兼容结构，并用轻量占位替换二进制内容。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"type": "binary", "size": len(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _safe_json_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_payload(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _safe_json_payload(value.model_dump(mode="python", exclude_none=True))
        except TypeError:
            return _safe_json_payload(value.model_dump())
    if is_dataclass(value):
        return {
            field.name: _safe_json_payload(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "__dict__"):
        return {
            key: _safe_json_payload(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and item is not None
        }
    if hasattr(value, "to_dict"):
        return _safe_json_payload(value.to_dict())
    try:
        return _safe_json_payload(jsonable_encoder(value))
    except Exception:
        return str(value)


def _event_payload(raw_event: Any) -> Any:
    """优先沿用 FastAPI 编码，遇到图片 bytes 等异常时降级为安全结构。"""

    try:
        return jsonable_encoder(raw_event)
    except Exception:
        return _safe_json_payload(raw_event)


def _active_run_payload(run: Any) -> dict[str, Any]:
    """仅抽取 runtime/active-run 恢复所需字段，避免序列化历史图片 bytes。"""

    payload = {
        "run_id": getattr(run, "run_id", None),
        "session_id": getattr(run, "session_id", None),
        "agent_id": getattr(run, "agent_id", None),
        "agent_name": getattr(run, "agent_name", None),
        "team_id": getattr(run, "team_id", None),
        "team_name": getattr(run, "team_name", None),
        "parent_run_id": getattr(run, "parent_run_id", None),
        "content": getattr(run, "content", None),
        "requirements": getattr(run, "requirements", None) or [],
        "tools": getattr(run, "tools", None) or [],
    }
    return _safe_json_payload(payload)


def _resolve_run_input_text(run: Any) -> str | None:
    """从 Agno run.input 中提取真实用户输入文本，避免使用 additional_input 历史。"""

    raw_input = getattr(run, "input", None)
    if raw_input is None:
        return None
    payload = _safe_json_payload(raw_input)
    if isinstance(payload, dict):
        for field_name in ("input_content", "content", "message", "input"):
            candidate = payload.get(field_name)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        nested_input = payload.get("input")
        if isinstance(nested_input, dict):
            for field_name in ("input_content", "content", "message"):
                candidate = nested_input.get(field_name)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return None


def _extract_text_content(value: Any) -> str | None:
    """仅提取适合直接渲染为助手正文的文本内容，避免把工具结构化结果误当成回答。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _raw_event_name(raw_event: Any, payload: dict[str, Any]) -> str:
    """读取 Agno 原始事件名，兼容 dict 与事件对象两种形态。"""

    return str(payload.get("event") or type(raw_event).__name__)


def _extract_member_event_data(payload: dict[str, Any]) -> dict[str, Any]:
    """从 Team 或成员事件中提取成员智能体标识，供前端工具详情展示。"""

    result: dict[str, Any] = {}
    parent_run_id = payload.get("parent_run_id")
    if parent_run_id is not None:
        result["parent_run_id"] = parent_run_id
        if payload.get("run_id") is not None:
            result["member_run_id"] = payload.get("run_id")
        if payload.get("agent_id") is not None:
            result["member_agent_id"] = payload.get("agent_id")
        if payload.get("agent_name") is not None:
            result["member_agent_name"] = payload.get("agent_name")
    for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
        if payload.get(field_name) is not None:
            result[field_name] = payload.get(field_name)
    tool_payload = payload.get("tool")
    if isinstance(tool_payload, dict):
        for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
            if field_name not in result and tool_payload.get(field_name) is not None:
                result[field_name] = tool_payload.get(field_name)
        field_aliases = {
            "member_agent_id": ("agent_id", "child_agent_id", "target_agent_id"),
            "member_agent_name": ("agent_name", "child_agent_name", "target_agent_name", "member_name"),
            "member_run_id": ("child_run_id", "target_run_id"),
        }
        for field_name, aliases in field_aliases.items():
            if field_name in result:
                continue
            for alias in aliases:
                if tool_payload.get(alias) is not None:
                    result[field_name] = tool_payload.get(alias)
                    break
    requirements = payload.get("requirements") or []
    if isinstance(requirements, list) and requirements:
        first_requirement = requirements[0]
        if isinstance(first_requirement, dict):
            for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
                if field_name not in result and first_requirement.get(field_name) is not None:
                    result[field_name] = first_requirement.get(field_name)
            nested_tool = first_requirement.get("tool_execution")
            if isinstance(nested_tool, dict):
                for field_name in ("member_agent_id", "member_agent_name", "member_run_id"):
                    if field_name not in result and nested_tool.get(field_name) is not None:
                        result[field_name] = nested_tool.get(field_name)
    return result


def _resolve_run_owner_id(payload: Any) -> str | None:
    """提取 Agno run 所属 Agent/Team ID。"""

    owner_id = getattr(payload, "agent_id", None) or getattr(payload, "team_id", None)
    return str(owner_id) if owner_id else None


def _coerce_run_status(status: Any) -> RunStatus:
    """把 Agno 或 JSON 化后的状态值统一为 RunStatus。"""

    if isinstance(status, RunStatus):
        return status
    if status is None:
        return RunStatus.running
    raw_status = str(status).lower()
    for candidate in RunStatus:
        if raw_status in {candidate.name.lower(), candidate.value.lower()}:
            return candidate
    return RunStatus.error


def _normalize_run_status_value(status: Any) -> str:
    """把 Agno RunStatus 映射为前端稳定状态字符串。"""

    normalized = _coerce_run_status(status)
    if normalized == RunStatus.error:
        return "failed"
    return normalized.name


def _run_latest_event_index(run: Any) -> int:
    """按 Agno run.events 计算当前可回放的最后事件下标。"""

    events = getattr(run, "events", None) or []
    return len(events) - 1


def _resolve_reasoning_content(value: Any, *, preserve_stream_boundary: bool = False) -> str | None:
    """从 Agno 消息或事件中提取 reasoning 字段。"""

    if isinstance(value, dict):
        for field_name in ("reasoning_content", "redacted_reasoning_content"):
            resolved = _normalize_reasoning_content(
                _stringify_content(value.get(field_name)),
                preserve_boundary=preserve_stream_boundary,
            )
            if resolved is not None:
                return resolved
        return None

    for field_name in ("reasoning_content", "redacted_reasoning_content"):
        resolved = _normalize_reasoning_content(
            _stringify_content(getattr(value, field_name, None)),
            preserve_boundary=preserve_stream_boundary,
        )
        if resolved is not None:
            return resolved
    return None


def _split_reasoning_content(
    content: str | None,
    reasoning_content: str | None = None,
    *,
    preserve_reasoning_boundary: bool = False,
) -> tuple[str | None, str | None]:
    """把正文中内嵌的 think/reasoning 标签拆成独立字段。"""

    resolved_reasoning = _normalize_reasoning_content(
        reasoning_content,
        preserve_boundary=preserve_reasoning_boundary,
    )
    if content is None:
        return None, resolved_reasoning

    stripped_content = content
    collected_reasoning: list[str] = []
    for pattern in (_REASONING_BLOCK_PATTERN, _THINK_BLOCK_PATTERN):
        matches = [match.strip() for match in pattern.findall(stripped_content) if match.strip()]
        if matches:
            collected_reasoning.extend(matches)
        stripped_content = pattern.sub("", stripped_content)
    open_tag_match = _OPEN_REASONING_TAG_PATTERN.search(stripped_content)
    if open_tag_match is not None:
        before_reasoning = stripped_content[: open_tag_match.start()]
        after_reasoning = stripped_content[open_tag_match.end() :].strip()
        if after_reasoning:
            collected_reasoning.append(after_reasoning)
        stripped_content = before_reasoning
    stripped_content = _REASONING_TAG_PATTERN.sub("", stripped_content)

    if collected_reasoning:
        reasoning_parts = [resolved_reasoning] if resolved_reasoning else []
        reasoning_parts.extend(collected_reasoning)
        resolved_reasoning = "\n\n".join(reasoning_parts)

    return stripped_content, resolved_reasoning


def _normalize_reasoning_content(value: str | None, *, preserve_boundary: bool = False) -> str | None:
    """规范化 reasoning 文本；流式片段需保留换行边界以便前端即时排版。"""

    if not isinstance(value, str):
        return None
    if preserve_boundary:
        return value if value else None
    stripped_value = value.strip()
    return stripped_value or None


def _timeline_content_from_event(
    *,
    event_name: str,
    payload: dict[str, Any],
    hide_member_events: bool = True,
) -> tuple[str | None, str | None]:
    """从 Agno 内容事件提取可直接进入时间线的 assistant 正文和 reasoning。"""

    member_event_data = _extract_member_event_data(payload)
    if hide_member_events and member_event_data.get("parent_run_id") and member_event_data.get("member_run_id"):
        return None, None
    if event_name in {
        "RunContent",
        "RunContentEvent",
        "IntermediateRunContent",
        "IntermediateRunContentEvent",
        "RunIntermediateContent",
        "TeamRunContent",
        "TeamRunIntermediateContent",
        "RunCompleted",
        "RunCompletedEvent",
        "TeamRunCompleted",
    }:
        return _split_reasoning_content(
            _extract_text_content(payload.get("content")),
            _resolve_reasoning_content(payload, preserve_stream_boundary=True),
            preserve_reasoning_boundary=True,
        )
    if event_name == "ReasoningContentDelta":
        return None, _resolve_reasoning_content(payload, preserve_stream_boundary=True)
    return None, None


def _is_timeline_completed_event(event_name: str) -> bool:
    """判断内容事件是否是终态聚合事件，避免与流式 delta 重复。"""

    return event_name in {"RunCompleted", "RunCompletedEvent", "TeamRunCompleted"}


def _timeline_run_status_content(status: str, run_content: Any) -> str:
    """生成运行状态时间线的紧凑文案。"""

    content = _extract_text_content(run_content)
    if status == "failed":
        return content or "运行失败。"
    if status == "cancelled":
        return content or "运行已停止。"
    if status == "paused":
        return "等待用户处理。"
    return "运行已完成。"


def _index_answered_ask_user_messages(
    messages: list[Any],
) -> tuple[dict[str, list[_AnsweredAskUserMessage]], dict[str, list[_AnsweredAskUserMessage]]]:
    """索引已回答 ask_user tool message，兼容 tool_call_id 变化时按问题文案回退匹配。"""

    by_call_id: dict[str, list[_AnsweredAskUserMessage]] = {}
    by_question: dict[str, list[_AnsweredAskUserMessage]] = {}
    for message_index, message in enumerate(messages):
        if str(_message_attr(message, "role", "") or "") != "tool":
            continue
        if _coerce_str(_message_attr(message, "tool_name", None)) != "ask_user":
            continue
        input_payload = _message_attr(message, "tool_args", None)
        output_payload = _message_tool_output_payload(message)
        answered = _AnsweredAskUserMessage(
            message_index=message_index,
            tool_call_id=_coerce_str(_message_attr(message, "tool_call_id", None)),
            input_payload=input_payload,
            output_payload=output_payload,
            questions=_ask_user_questions_from_payload(input_payload),
            message=_message_tool_error_text(message) or "",
            created_at=_normalize_timestamp(_message_attr(message, "created_at", None)),
        )
        if answered.tool_call_id:
            by_call_id.setdefault(answered.tool_call_id, []).append(answered)
        for question in answered.questions:
            by_question.setdefault(question, []).append(answered)
    return by_call_id, by_question


def _pop_answered_ask_user_message(
    requirement: AgentPendingRequirement,
    *,
    by_call_id: dict[str, list[_AnsweredAskUserMessage]],
    by_question: dict[str, list[_AnsweredAskUserMessage]],
) -> _AnsweredAskUserMessage | None:
    """按 tool_call_id 优先、问题文案其次，消费一条已回答 ask_user message。"""

    if requirement.tool_name != "ask_user" and requirement.kind != "user_feedback":
        return None
    tool_call_id = _coerce_str(requirement.tool_execution.get("tool_call_id"))
    if tool_call_id:
        candidates = by_call_id.get(tool_call_id) or []
        if candidates:
            return candidates.pop(0)
    for question in _ask_user_questions_from_payload(requirement.tool_execution):
        candidates = by_question.get(question) or []
        if candidates:
            return candidates.pop(0)
    for item in requirement.user_feedback_schema or []:
        if not isinstance(item, dict):
            continue
        question = _coerce_str(item.get("question"))
        if not question:
            continue
        candidates = by_question.get(question) or []
        if candidates:
            return candidates.pop(0)
    return None


def _ask_user_questions_from_payload(payload: Any) -> list[str]:
    """从 ask_user 参数结构中提取问题文案。"""

    if not isinstance(payload, dict):
        return []
    raw_questions = payload.get("questions") or payload.get("user_feedback_schema")
    if raw_questions is None and isinstance(payload.get("tool_args"), dict):
        raw_questions = payload["tool_args"].get("questions") or payload["tool_args"].get("user_feedback_schema")
    if not isinstance(raw_questions, list):
        return []
    questions: list[str] = []
    for item in raw_questions:
        if isinstance(item, dict):
            question = _coerce_str(item.get("question"))
            if question:
                questions.append(question)
    return questions


def _tool_status_from_agno_event(event_name: str) -> str | None:
    """把 Agno 工具事件名映射到前端工具状态。"""

    if event_name in {"ToolCallStarted", "ToolCallStartedEvent", "TeamToolCallStarted"}:
        return "running"
    if event_name in {"ToolCallCompleted", "ToolCallCompletedEvent", "TeamToolCallCompleted"}:
        return "completed"
    if event_name in {"ToolCallError", "ToolCallErrorEvent", "TeamToolCallError"}:
        return "error"
    return None


def _resolve_tool_detail_id_for_agno(
    *,
    run_id: str,
    tool_name: str,
    tool_call_id: str | None,
    event_name: str,
    event_index: int,
    pending_without_call_id: dict[tuple[str, str], str],
) -> str:
    """为 Agno 工具事件生成稳定详情 ID。"""

    if tool_call_id:
        return f"{run_id}:{tool_call_id}"
    key = (run_id, tool_name)
    if event_name in {"ToolCallStarted", "ToolCallStartedEvent", "TeamToolCallStarted"}:
        detail_id = f"{run_id}:{tool_name}:{event_index}"
        pending_without_call_id[key] = detail_id
        return detail_id
    return pending_without_call_id.get(key) or f"{run_id}:{tool_name}:{event_index}"
