"""文件功能：从平台消息、事件与工具账本派生失败 Run 的安全可恢复模型历史。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_agent_runtime import AiAgentMessage, AiAgentRun, AiAgentRunEvent, AiAgentToolCall

_TERMINAL_RECOVERY_STATUSES = {"failed", "cancelled"}
_TERMINAL_EVENT_NAMES = {"run.error", "run.cancelled"}


@dataclass(slots=True)
class RunHistoryRecoveryDiagnostics:
    """记录单个 Run 的历史恢复动作，供测试和只读诊断复用。"""

    raw_message_count: int = 0
    recovered_message_count: int = 0
    user_input_restored: bool = False
    restored_tool_call_ids: list[str] = field(default_factory=list)
    trimmed_tool_call_ids: list[str] = field(default_factory=list)
    draft_length: int = 0
    last_checkpoint_phase: str = "none"

    def model_dump(self) -> dict[str, Any]:
        """返回可直接写入诊断结果的 JSON 结构。"""

        return {
            "raw_message_count": self.raw_message_count,
            "recovered_message_count": self.recovered_message_count,
            "user_input_restored": self.user_input_restored,
            "restored_tool_call_ids": list(self.restored_tool_call_ids),
            "trimmed_tool_call_ids": list(self.trimmed_tool_call_ids),
            "draft_length": self.draft_length,
            "last_checkpoint_phase": self.last_checkpoint_phase,
        }


@dataclass(slots=True)
class RecoveredRunHistory:
    """包含可交给模型的 Run delta 与恢复诊断。"""

    message_json: list[dict[str, Any]]
    diagnostics: RunHistoryRecoveryDiagnostics


async def recover_run_message_history(
    *,
    session: AsyncSession,
    run_model: AiAgentRun,
) -> RecoveredRunHistory:
    """按持久化事实修复单个 Run 历史，不修改任何数据库记录。"""

    raw_messages = _message_dicts(run_model.message_history_json)
    diagnostics = RunHistoryRecoveryDiagnostics(raw_message_count=len(raw_messages))
    events = await _load_run_events(session, run_model.run_id)
    tools = await _load_run_tools(session, run_model.run_id)
    diagnostics.last_checkpoint_phase = _last_checkpoint_phase(events)

    reconciled, restored_ids = _reconcile_completed_tools(raw_messages, tools)
    diagnostics.restored_tool_call_ids = restored_ids
    safe_messages, trimmed_ids, dropped_text = _trim_unprocessed_tool_tail(reconciled)
    # 同一模型响应可能同时包含已完成与结果未知工具；裁掉未知调用后重新补回已确认事实。
    safe_messages, restored_after_trim = _reconcile_completed_tools(safe_messages, tools)
    restored_ids = [*restored_ids, *[item for item in restored_after_trim if item not in restored_ids]]
    diagnostics.trimmed_tool_call_ids = trimmed_ids

    if run_model.status in _TERMINAL_RECOVERY_STATUSES:
        if not _contains_user_prompt(safe_messages):
            user_message = await _load_user_message(session, run_model.run_id)
            safe_messages = [
                *_build_user_request(run_model, user_message),
                *safe_messages,
            ]
            diagnostics.user_input_restored = True
        draft = _collect_incomplete_draft(events, dropped_text=dropped_text, existing_history=safe_messages)
        notice = _build_interruption_notice(run_model, tools=tools, draft=draft)
        if notice:
            safe_messages.extend(notice)
        diagnostics.draft_length = len(draft)

    diagnostics.recovered_message_count = len(safe_messages)
    return RecoveredRunHistory(message_json=safe_messages, diagnostics=diagnostics)


async def _load_run_events(session: AsyncSession, run_id: str) -> list[AiAgentRunEvent]:
    """按事件游标读取 Run 事件。"""

    result = await session.execute(
        select(AiAgentRunEvent)
        .where(AiAgentRunEvent.run_id == run_id)
        .order_by(AiAgentRunEvent.event_index.asc(), AiAgentRunEvent.id.asc())
    )
    return list(result.scalars().all())


async def _load_run_tools(session: AsyncSession, run_id: str) -> list[AiAgentToolCall]:
    """按落库顺序读取权威工具执行账本。"""

    result = await session.execute(
        select(AiAgentToolCall)
        .where(AiAgentToolCall.run_id == run_id)
        .order_by(AiAgentToolCall.id.asc())
    )
    return list(result.scalars().all())


async def _load_user_message(session: AsyncSession, run_id: str) -> AiAgentMessage | None:
    """读取 Run 创建时已持久化的用户消息。"""

    result = await session.execute(
        select(AiAgentMessage)
        .where(AiAgentMessage.run_id == run_id, AiAgentMessage.role == "user")
        .order_by(AiAgentMessage.order_index.asc(), AiAgentMessage.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _reconcile_completed_tools(
    messages: list[dict[str, Any]],
    tools: list[AiAgentToolCall],
) -> tuple[list[dict[str, Any]], list[str]]:
    """用工具账本补齐已完成或明确失败的工具链，并按调用 ID 去重。"""

    reconciled = _message_dicts(messages)
    call_ids, return_ids = _tool_history_ids(reconciled)
    restored_ids: list[str] = []
    for tool in tools:
        tool_call_id = str(tool.tool_call_id or "").strip()
        if not tool_call_id or tool.status not in {"completed", "error"}:
            continue
        if tool.status == "error" and tool.output_payload_json is None and not str(tool.message or "").strip():
            continue
        restored = False
        if tool_call_id not in call_ids:
            reconciled.extend(_dump_messages([
                ModelResponse(parts=[
                    ToolCallPart(
                        tool_name=tool.tool_name,
                        args=tool.input_payload_json if tool.input_payload_json is not None else {},
                        tool_call_id=tool_call_id,
                    )
                ])
            ]))
            call_ids.add(tool_call_id)
            restored = True
        if tool_call_id not in return_ids:
            content = tool.output_payload_json
            if tool.status == "error":
                content = {
                    "status": "error",
                    "message": str(tool.message or "工具执行失败。"),
                    "result": tool.output_payload_json,
                }
            reconciled.extend(_dump_messages([
                ModelRequest(parts=[
                    ToolReturnPart(
                        tool_name=tool.tool_name,
                        content=content,
                        tool_call_id=tool_call_id,
                    )
                ])
            ]))
            return_ids.add(tool_call_id)
            restored = True
        if restored:
            restored_ids.append(tool_call_id)
    return reconciled, restored_ids


def _trim_unprocessed_tool_tail(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], str]:
    """裁剪仍未闭合的工具调用，并提取被裁剪的可见文本作为未完成草稿。"""

    messages = _drop_orphan_tool_results(messages)
    pending: dict[str, int] = {}
    for message_index, message in enumerate(messages):
        for part_index, part in enumerate(message.get("parts") if isinstance(message.get("parts"), list) else []):
            if not isinstance(part, dict):
                continue
            part_kind = str(part.get("part_kind") or "")
            tool_call_id = str(part.get("tool_call_id") or "").strip()
            if part_kind == "tool-call":
                pending[tool_call_id or f"__missing__:{message_index}:{part_index}"] = message_index
            elif part_kind in {"tool-return", "retry-prompt"} and tool_call_id:
                pending.pop(tool_call_id, None)
    if not pending:
        return messages, [], ""
    cut_index = min(pending.values())
    dropped_text = _visible_text(messages[cut_index:])
    trimmed_ids = [key for key, index in pending.items() if index >= cut_index and not key.startswith("__missing__:")]
    return messages[:cut_index], trimmed_ids, dropped_text


def _drop_orphan_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """移除没有前置调用的工具返回，避免旧坏数据破坏模型消息序列。"""

    repaired: list[dict[str, Any]] = []
    pending_ids: set[str] = set()
    for message in messages:
        parts = message.get("parts") if isinstance(message.get("parts"), list) else []
        call_ids = {
            str(part.get("tool_call_id") or "").strip()
            for part in parts
            if isinstance(part, dict) and part.get("part_kind") == "tool-call" and str(part.get("tool_call_id") or "").strip()
        }
        if call_ids:
            repaired.append(message)
            pending_ids = call_ids
            continue
        if not any(isinstance(part, dict) and part.get("part_kind") in {"tool-return", "retry-prompt"} for part in parts):
            repaired.append(message)
            pending_ids = set()
            continue
        kept_parts = [
            part
            for part in parts
            if not isinstance(part, dict)
            or part.get("part_kind") not in {"tool-return", "retry-prompt"}
            or str(part.get("tool_call_id") or "").strip() in pending_ids
        ]
        matched_ids = {
            str(part.get("tool_call_id") or "").strip()
            for part in kept_parts
            if isinstance(part, dict) and part.get("part_kind") in {"tool-return", "retry-prompt"}
        }
        if kept_parts:
            repaired.append({**message, "parts": kept_parts})
        pending_ids -= matched_ids
    return repaired


def _build_user_request(run_model: AiAgentRun, message: AiAgentMessage | None) -> list[dict[str, Any]]:
    """从平台消息和轻量图片引用重建用户请求。"""

    payload = run_model.input_payload_json if isinstance(run_model.input_payload_json, dict) else {}
    content = str((message.content if message is not None else None) or payload.get("message") or "").strip()
    image_ids = [item for item in payload.get("image_attachment_ids", []) if isinstance(item, int) and item > 0]
    user_content: str | list[Any] = content
    if image_ids:
        user_content = [content or "请参考所附图片。", *[
            {"kind": "agent-image-ref", "attachment_id": attachment_id, "source_kind": "user_upload"}
            for attachment_id in image_ids
        ]]
    return _dump_messages([ModelRequest(parts=[UserPromptPart(content=user_content)])])


def _build_interruption_notice(
    run_model: AiAgentRun,
    *,
    tools: list[AiAgentToolCall],
    draft: str,
) -> list[dict[str, Any]]:
    """构造明确区分平台事实与未完成草稿的恢复说明。"""

    unknown_tools = [
        f"{tool.tool_name}(tool_call_id={tool.tool_call_id or 'unknown'})"
        for tool in tools
        if tool.status in {"running", "interrupted"}
    ]
    parts = [
        "上一轮智能体运行在完成前中断。",
        f"run_id={run_model.run_id}；status={run_model.status}；error_code={run_model.error_code or 'none'}。",
    ]
    if unknown_tools:
        parts.append(
            "以下工具执行结果未知，不得假设成功，也不得直接重试写操作；必须先查询目标实体当前状态："
            + "、".join(unknown_tools)
            + "。"
        )
    if draft:
        parts.append("以下是上一轮未完成的可见草稿，仅供参考，不代表最终结论或已完成承诺：\n<interrupted_draft>\n" + draft + "\n</interrupted_draft>")
    return _dump_messages([ModelRequest(parts=[SystemPromptPart(content="\n".join(parts))])])


def _collect_incomplete_draft(
    events: list[AiAgentRunEvent],
    *,
    dropped_text: str,
    existing_history: list[dict[str, Any]],
) -> str:
    """收集最后检查点后的可见增量，排除 reasoning 与已存在的完整文本。"""

    last_completed_index = max(
        (event.event_index for event in events if event.event == "model.request.completed"),
        default=-1,
    )
    chunks = [
        str(event.payload_json.get("content") or "")
        for event in events
        if event.event_index > last_completed_index
        and event.event == "message.delta"
        and isinstance(event.payload_json, dict)
    ]
    candidates = [dropped_text.strip(), "".join(chunks).strip()]
    existing_text = _visible_text(existing_history)
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in existing_text and candidate not in unique:
            unique.append(candidate)
    return "\n\n".join(unique)


def _last_checkpoint_phase(events: list[AiAgentRunEvent]) -> str:
    """根据已提交事件推断最后有效检查点阶段。"""

    if any(event.event in {"tool.completed", "tool.error"} for event in events):
        return "tool"
    if any(event.event == "model.request.completed" for event in events):
        return "model"
    if any(event.event == "run.started" for event in events):
        return "input"
    return "none"


def _contains_user_prompt(messages: list[dict[str, Any]]) -> bool:
    """判断 Run delta 是否已经包含用户输入。"""

    return any(
        isinstance(part, dict) and str(part.get("part_kind") or "") == "user-prompt"
        for message in messages
        for part in (message.get("parts") if isinstance(message.get("parts"), list) else [])
    )


def _tool_history_ids(messages: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """提取历史中已有工具调用和返回 ID。"""

    call_ids: set[str] = set()
    return_ids: set[str] = set()
    for message in messages:
        for part in message.get("parts") if isinstance(message.get("parts"), list) else []:
            if not isinstance(part, dict):
                continue
            tool_call_id = str(part.get("tool_call_id") or "").strip()
            if not tool_call_id:
                continue
            if part.get("part_kind") == "tool-call":
                call_ids.add(tool_call_id)
            elif part.get("part_kind") in {"tool-return", "retry-prompt"}:
                return_ids.add(tool_call_id)
    return call_ids, return_ids


def _visible_text(messages: list[dict[str, Any]]) -> str:
    """提取模型响应中的可见正文，明确忽略 reasoning。"""

    chunks: list[str] = []
    for message in messages:
        if message.get("kind") != "response":
            continue
        for part in message.get("parts") if isinstance(message.get("parts"), list) else []:
            if isinstance(part, dict) and part.get("part_kind") == "text":
                content = str(part.get("content") or "").strip()
                if content:
                    chunks.append(content)
    return "\n".join(chunks)


def _message_dicts(value: Any) -> list[dict[str, Any]]:
    """复制合法消息字典，避免派生恢复过程修改 ORM JSON 原值。"""

    return [dict(item) for item in value] if isinstance(value, list) else []


def _dump_messages(messages: list[ModelRequest | ModelResponse]) -> list[dict[str, Any]]:
    """把 Pydantic AI 消息稳定序列化为 JSON 字典。"""

    dumped = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    return [dict(item) for item in dumped] if isinstance(dumped, list) else []
