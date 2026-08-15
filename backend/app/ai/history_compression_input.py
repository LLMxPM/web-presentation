"""文件功能：构造 Agent 历史压缩专用的结构化输入，并规整工具交互载荷。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.image_refs import sanitize_message_history_image_refs
from app.ai.history_compression_values import (
    ENCODING as _ENCODING,
    MAX_COMPACTION_LEVEL,
    MESSAGE_SOFT_LIMIT_TOKENS,
    TOOL_ARGS_SOFT_LIMIT_TOKENS,
    TOOL_RESULT_SOFT_LIMIT_TOKENS,
    collect_important_scalars as _collect_important_scalars,
    compact_value as _compact_value,
    contains_truncation as _contains_truncation,
    render_item_line as _render_item_line,
    strip_internal_fields as _strip_internal_fields,
    truncate_text_by_tokens as _truncate_text_by_tokens,
)
from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentRun, AiAgentToolCall

COMPRESSION_INPUT_SCHEMA_VERSION = "agent-compression-input.v1"

_SUMMARY_MARKER = "以下为较早智能体会话历史摘要，已替代压缩边界之前的原始消息："
_RUN_CONTEXT_KEYS = (
    "run_id",
    "workspace_id",
    "project_id",
    "page_id",
    "component_id",
    "scope_type",
    "source",
    "allowed_projects",
)
@dataclass(slots=True)
class CompressionInputStats:
    """描述压缩输入的结构规模和确定性规整结果。"""

    raw_message_count: int
    normalized_item_count: int
    run_count: int
    tool_interaction_count: int
    unknown_tool_count: int
    truncated_result_count: int
    estimated_input_tokens: int
    compaction_level: int

    def model_dump(self) -> dict[str, int]:
        """返回事件和诊断可直接使用的统计字典。"""

        return {
            "raw_message_count": self.raw_message_count,
            "normalized_item_count": self.normalized_item_count,
            "run_count": self.run_count,
            "tool_interaction_count": self.tool_interaction_count,
            "unknown_tool_count": self.unknown_tool_count,
            "truncated_result_count": self.truncated_result_count,
            "estimated_input_tokens": self.estimated_input_tokens,
            "compaction_level": self.compaction_level,
        }


@dataclass(slots=True)
class CompressionInput:
    """描述一次压缩模型请求使用的结构化历史输入。"""

    payload: dict[str, Any]
    serialized_text: str
    stats: CompressionInputStats
    sources: "CompressionInputSources | None" = None


@dataclass(slots=True)
class CompressionInputSources:
    """缓存一次压缩所需的 Run 和工具账本，避免分级规整重复查询数据库。"""

    run_contexts: dict[str, dict[str, Any]]
    ledger_rows: list[dict[str, Any]]


async def build_compression_input(
    *,
    prefix: Sequence[ModelMessage],
    session: AsyncSession,
    user_id: int,
    session_id: str,
    compaction_level: int = 0,
    sources: CompressionInputSources | None = None,
) -> CompressionInput:
    """从模型消息和工具账本构造只读的结构化压缩输入。"""

    dumped = ModelMessagesTypeAdapter.dump_python(list(prefix), mode="json")
    sanitized = sanitize_message_history_image_refs(dumped)
    messages = [dict(item) for item in sanitized if isinstance(item, dict)] if isinstance(sanitized, list) else []
    return await _build_from_message_dicts(
        messages=messages,
        session=session,
        user_id=user_id,
        session_id=session_id,
        compaction_level=compaction_level,
        sources=sources,
    )


def build_local_compression_input(
    messages: Sequence[ModelMessage],
    *,
    compaction_level: int = MAX_COMPACTION_LEVEL,
) -> CompressionInput:
    """在没有数据库工具账本时，按消息历史构造确定性压缩输入。"""

    dumped = ModelMessagesTypeAdapter.dump_python(list(messages), mode="json")
    sanitized = sanitize_message_history_image_refs(dumped)
    message_dicts = [dict(item) for item in sanitized if isinstance(item, dict)] if isinstance(sanitized, list) else []
    items = _normalize_message_items(
        message_dicts,
        run_contexts={},
        ledger_rows=[],
        compaction_level=compaction_level,
    )
    return _build_input_payload(message_dicts, items, compaction_level=compaction_level)


def render_deterministic_compression_text(
    compression_input: CompressionInput,
    *,
    previous_summary: str,
    target_tokens: int,
) -> str:
    """把结构化输入渲染成可安全截断的确定性事实摘要。"""

    lines: list[str] = []
    if previous_summary:
        lines.extend(["既有摘要：", previous_summary, ""])
    lines.append("结构化历史事实：")
    for item in compression_input.payload.get("items", []):
        if not isinstance(item, dict):
            continue
        lines.append(_render_item_line(item))
    return _truncate_text_by_tokens("\n".join(lines), target_tokens)


async def _build_from_message_dicts(
    *,
    messages: list[dict[str, Any]],
    session: AsyncSession,
    user_id: int,
    session_id: str,
    compaction_level: int,
    sources: CompressionInputSources | None = None,
) -> CompressionInput:
    """批量加载 Run 与工具账本后构造结构化压缩输入。"""

    run_ids = _collect_run_ids(messages)
    resolved_sources = sources or CompressionInputSources(
        run_contexts=await _load_run_contexts(
            session=session,
            user_id=user_id,
            session_id=session_id,
            run_ids=run_ids,
        ),
        ledger_rows=await _load_tool_ledger(
            session=session,
            user_id=user_id,
            session_id=session_id,
        ),
    )
    items = _normalize_message_items(
        messages,
        run_contexts=resolved_sources.run_contexts,
        ledger_rows=resolved_sources.ledger_rows,
        compaction_level=compaction_level,
    )
    result = _build_input_payload(messages, items, compaction_level=compaction_level)
    result.sources = resolved_sources
    return result


async def _load_tool_ledger(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
) -> list[dict[str, Any]]:
    """按用户和会话批量读取工具账本，避免压缩时逐工具查询。"""

    result = await session.execute(
        select(AiAgentToolCall)
        .join(AiAgentRun, AiAgentToolCall.run_id == AiAgentRun.run_id)
        .where(
            AiAgentRun.user_id == user_id,
            AiAgentRun.session_id == session_id,
        )
        .order_by(AiAgentToolCall.id.asc())
    )
    return [
        {
            "id": item.id,
            "run_id": item.run_id,
            "member_run_id": item.member_run_id,
            "tool_call_id": item.tool_call_id,
            "tool_name": item.tool_name,
            "status": item.status,
            "input_payload": item.input_payload_json,
            "output_payload": item.output_payload_json,
            "message": item.message,
        }
        for item in result.scalars().all()
    ]


async def _load_run_contexts(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
    run_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """读取普通 Run 和成员 Run 的权威分区快照。"""

    if not run_ids:
        return {}
    result = await session.execute(
        select(AiAgentRun).where(
            AiAgentRun.user_id == user_id,
            AiAgentRun.session_id == session_id,
            AiAgentRun.run_id.in_(run_ids),
        )
    )
    contexts = {
        item.run_id: _run_context_from_run(item)
        for item in result.scalars().all()
    }
    member_result = await session.execute(
        select(AiAgentMemberRun, AiAgentRun)
        .join(AiAgentRun, AiAgentMemberRun.parent_run_id == AiAgentRun.run_id)
        .where(
            AiAgentRun.user_id == user_id,
            AiAgentRun.session_id == session_id,
            AiAgentMemberRun.member_run_id.in_(run_ids),
        )
    )
    for member_run, parent_run in member_result.all():
        context = _run_context_from_run(parent_run)
        context.update(
            {
                "run_id": member_run.member_run_id,
                "member_run_id": member_run.member_run_id,
                "member_agent_id": member_run.agent_id,
                "member_agent_name": member_run.agent_name,
                "source": f"member:{member_run.agent_id}",
            }
        )
        contexts[member_run.member_run_id] = context
    return contexts


def _normalize_message_items(
    messages: list[dict[str, Any]],
    *,
    run_contexts: Mapping[str, dict[str, Any]],
    ledger_rows: list[dict[str, Any]],
    compaction_level: int,
) -> list[dict[str, Any]]:
    """按消息顺序生成 Run、正文和工具交互项。"""

    items: list[dict[str, Any]] = []
    pending: dict[tuple[str, str], dict[str, Any]] = {}
    emitted_contexts: set[str] = set()
    current_run_id = ""
    for message_index, message in enumerate(messages):
        if _is_summary_message(message):
            continue
        run_id = _message_run_id(message) or current_run_id
        if run_id:
            current_run_id = run_id
            if run_id not in emitted_contexts:
                items.append({"kind": "run_context", **_message_run_context(message, run_id, run_contexts)})
                emitted_contexts.add(run_id)
        parts = message.get("parts") if isinstance(message.get("parts"), list) else []
        for part_index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            part_kind = str(part.get("part_kind") or "")
            if part_kind == "tool-call":
                call_id = str(part.get("tool_call_id") or "").strip()
                key = (run_id, call_id or f"__missing__:{message_index}:{part_index}")
                record = {
                    "kind": "tool_interaction",
                    "run_id": run_id or None,
                    "tool_name": str(part.get("tool_name") or "unknown"),
                    "tool_call_id": call_id or None,
                    "_args": part.get("args"),
                    "_result": None,
                    "_message": None,
                    "_has_return": False,
                    "_retry": False,
                }
                items.append(record)
                pending[key] = record
                continue
            if part_kind in {"tool-return", "retry-prompt"}:
                record = _find_pending_tool(pending, run_id=run_id, call_id=part.get("tool_call_id"))
                if record is None:
                    items.append(
                        {
                            "kind": "orphan_tool_return",
                            "run_id": run_id or None,
                            "tool_name": str(part.get("tool_name") or "unknown"),
                            "tool_call_id": str(part.get("tool_call_id") or "") or None,
                            "status": "unknown",
                            "must_verify": True,
                            "result": _compact_value(part.get("content"), level=compaction_level, max_tokens=TOOL_RESULT_SOFT_LIMIT_TOKENS),
                        }
                    )
                    continue
                record["_has_return"] = True
                record["_result"] = part.get("content")
                record["_retry"] = part_kind == "retry-prompt"
                if part_kind == "retry-prompt":
                    record["_message"] = part.get("content")
                continue
            if part_kind == "user-prompt":
                items.append(
                    {
                        "kind": "user_message",
                        "run_id": run_id or None,
                        "content": _compact_value(part.get("content"), level=compaction_level, max_tokens=MESSAGE_SOFT_LIMIT_TOKENS),
                    }
                )
                continue
            if part_kind == "text":
                items.append(
                    {
                        "kind": "assistant_message",
                        "run_id": run_id or None,
                        "content": _compact_value(part.get("content"), level=compaction_level, max_tokens=MESSAGE_SOFT_LIMIT_TOKENS),
                    }
                )
                continue
            if part_kind == "system-prompt":
                items.append(
                    {
                        "kind": "system_notice",
                        "run_id": run_id or None,
                        "content": _compact_value(part.get("content"), level=compaction_level, max_tokens=MESSAGE_SOFT_LIMIT_TOKENS),
                    }
                )
                continue
            if part_kind:
                items.append(
                    {
                        "kind": "message_part",
                        "run_id": run_id or None,
                        "part_kind": part_kind,
                        "content": _compact_value(part.get("content"), level=compaction_level, max_tokens=1_024),
                        "tool_name": str(part.get("tool_name") or "") or None,
                    }
                )
    for item in items:
        if item.get("kind") != "tool_interaction":
            continue
        _finalize_tool_item(item, ledger_rows=ledger_rows, compaction_level=compaction_level)
    return [_strip_internal_fields(item) for item in items]


def _finalize_tool_item(item: dict[str, Any], *, ledger_rows: list[dict[str, Any]], compaction_level: int) -> None:
    """用工具账本确定交互状态并压缩参数、结果和关键 ID。"""

    ledger = _select_ledger_row(
        ledger_rows,
        run_id=str(item.get("run_id") or ""),
        call_id=str(item.get("tool_call_id") or ""),
        tool_name=str(item.get("tool_name") or ""),
    )
    ledger_status = str((ledger or {}).get("status") or "").strip()
    has_return = bool(item.pop("_has_return", False))
    is_retry = bool(item.pop("_retry", False))
    raw_args = (ledger or {}).get("input_payload") if ledger and _meaningful((ledger or {}).get("input_payload")) else item.pop("_args", None)
    raw_result = (ledger or {}).get("output_payload") if ledger and (ledger or {}).get("output_payload") is not None else item.pop("_result", None)
    raw_message = (ledger or {}).get("message") if ledger and str((ledger or {}).get("message") or "").strip() else item.pop("_message", None)
    if ledger_status in {"completed"}:
        status = "completed"
    elif ledger_status in {"error"}:
        status = "error"
    elif ledger_status in {"running", "waiting_external", "interrupted", "cancelled"}:
        status = "unknown"
    elif is_retry:
        status = "retry_required"
    elif has_return:
        status = "returned"
    else:
        status = "unknown"
    item["status"] = status
    if status == "unknown":
        item["must_verify"] = True
    compact_args = _compact_value(raw_args, level=compaction_level, max_tokens=TOOL_ARGS_SOFT_LIMIT_TOKENS)
    compact_result = _compact_value(raw_result, level=compaction_level, max_tokens=TOOL_RESULT_SOFT_LIMIT_TOKENS)
    if compact_args not in (None, {}, ""):
        item["args"] = compact_args
    if compact_result not in (None, {}, ""):
        item["result"] = compact_result
    if raw_message:
        item["message"] = _compact_value(raw_message, level=compaction_level, max_tokens=1_024)
    important_ids = _collect_important_scalars(raw_args)
    important_ids.update(_collect_important_scalars(raw_result))
    if important_ids:
        item["important_ids"] = important_ids


def _build_input_payload(messages: list[dict[str, Any]], items: list[dict[str, Any]], *, compaction_level: int) -> CompressionInput:
    """生成版本化输入包和统计信息。"""

    tool_items = [item for item in items if item.get("kind") == "tool_interaction"]
    unknown_tools = [item for item in tool_items if item.get("status") == "unknown"]
    truncated = [item for item in items if _contains_truncation(item)]
    payload = {
        "schema_version": COMPRESSION_INPUT_SCHEMA_VERSION,
        "items": items,
        "stats": {
            "run_count": len({str(item.get("run_id")) for item in items if item.get("run_id")}),
            "tool_interaction_count": len(tool_items),
            "unknown_tool_count": len(unknown_tools),
            "truncated_result_count": len(truncated),
        },
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    stats = CompressionInputStats(
        raw_message_count=len(messages),
        normalized_item_count=len(items),
        run_count=int(payload["stats"]["run_count"]),
        tool_interaction_count=len(tool_items),
        unknown_tool_count=len(unknown_tools),
        truncated_result_count=len(truncated),
        estimated_input_tokens=len(_ENCODING.encode(serialized)),
        compaction_level=max(0, min(MAX_COMPACTION_LEVEL, int(compaction_level))),
    )
    return CompressionInput(payload=payload, serialized_text=serialized, stats=stats)


def _find_pending_tool(pending: Mapping[tuple[str, str], dict[str, Any]], *, run_id: str, call_id: Any) -> dict[str, Any] | None:
    """按 Run 和调用 ID 查找未完成工具；缺失 Run 时使用最近匹配。"""

    normalized = str(call_id or "").strip()
    if not normalized:
        return None
    direct = pending.get((run_id, normalized))
    if direct is not None:
        return direct
    matches = [record for (candidate_run, candidate_id), record in pending.items() if candidate_id == normalized]
    return matches[-1] if matches else None


def _select_ledger_row(ledger_rows: Iterable[dict[str, Any]], *, run_id: str, call_id: str, tool_name: str) -> dict[str, Any] | None:
    """选择与历史工具调用最匹配的账本行，兼容成员调用 ID 前缀。"""

    rows = [row for row in ledger_rows if str(row.get("tool_name") or "") == tool_name]
    exact = [row for row in rows if str(row.get("tool_call_id") or "") == call_id]
    same_run = [row for row in exact if str(row.get("run_id") or "") == run_id or str(row.get("member_run_id") or "") == run_id]
    if same_run:
        return max(same_run, key=lambda row: int(row.get("id") or 0))
    if exact:
        return max(exact, key=lambda row: int(row.get("id") or 0))
    suffix = [
        row
        for row in rows
        if call_id and str(row.get("tool_call_id") or "").endswith(f":{call_id}")
    ]
    same_suffix_run = [row for row in suffix if str(row.get("member_run_id") or "") == run_id]
    if same_suffix_run:
        return max(same_suffix_run, key=lambda row: int(row.get("id") or 0))
    return max(suffix, key=lambda row: int(row.get("id") or 0)) if suffix else None


def _collect_run_ids(messages: Sequence[dict[str, Any]]) -> set[str]:
    """从消息字段和首个请求 metadata 收集 Run ID。"""

    result: set[str] = set()
    for message in messages:
        run_id = _message_run_id(message)
        if run_id:
            result.add(run_id)
    return result


def _message_run_id(message: Mapping[str, Any]) -> str:
    """读取消息自身或 metadata 中的 Run ID。"""

    direct = str(message.get("run_id") or "").strip()
    if direct:
        return direct
    metadata = message.get("metadata")
    return str(metadata.get("run_id") or "").strip() if isinstance(metadata, dict) else ""


def _message_run_context(
    message: Mapping[str, Any],
    run_id: str,
    run_contexts: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """构造 Run 分区；无数据库快照时回退到消息首个请求的 metadata。"""

    context = dict(run_contexts.get(run_id) or {})
    metadata = message.get("metadata")
    if isinstance(metadata, Mapping):
        for key in _RUN_CONTEXT_KEYS:
            if key not in context and key in metadata:
                context[key] = metadata[key]
    context.setdefault("run_id", run_id)
    return context


def _run_context_from_run(run: AiAgentRun) -> dict[str, Any]:
    """把普通 Run 快照转为压缩输入分区。"""

    payload = run.input_payload_json if isinstance(run.input_payload_json, dict) else {}
    allowed_projects = payload.get("allowed_projects") if isinstance(payload.get("allowed_projects"), list) else []
    return {
        "run_id": run.run_id,
        "workspace_id": run.workspace_id,
        "project_id": run.project_id,
        "page_id": run.page_id,
        "component_id": run.component_id,
        "scope_type": run.scope_type,
        "source": run.source,
        "allowed_projects": allowed_projects,
    }


def _is_summary_message(message: Mapping[str, Any]) -> bool:
    """识别平台生成的历史摘要消息，避免与 previous_summary 重复输入。"""

    if message.get("kind") != "request":
        return False
    parts = message.get("parts") if isinstance(message.get("parts"), list) else []
    return any(
        isinstance(part, dict)
        and part.get("part_kind") == "user-prompt"
        and _SUMMARY_MARKER in str(part.get("content") or "")
        for part in parts
    )


def _meaningful(value: Any) -> bool:
    """判断工具账本载荷是否有可用于压缩的内容。"""

    return value is not None and value != {} and value != [] and value != ""
