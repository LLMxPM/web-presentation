"""文件功能：提供 Agent 会话 Facade 共用的序列化、文本归一和 Agno run 读取辅助函数。"""

from __future__ import annotations

import json
import re
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from agno.run.agent import RunOutput
from agno.run.base import RunStatus
from agno.run.team import TeamRunOutput
from agno.session.agent import AgentSession
from agno.session.team import TeamSession
from fastapi.encoders import jsonable_encoder

_REASONING_BLOCK_PATTERN = re.compile(r"<reasoning>(.*?)</reasoning>", re.IGNORECASE | re.DOTALL)
_THINK_BLOCK_PATTERN = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
_OPEN_REASONING_TAG_PATTERN = re.compile(r"<(?:reasoning|think)>", re.IGNORECASE)
_REASONING_TAG_PATTERN = re.compile(r"</?(?:reasoning|think)>", re.IGNORECASE)
AgnoSessionDetail = AgentSession | TeamSession


def _coerce_int(value: Any) -> int | None:
    """把 metadata 中的数字字段安全转为 int。"""

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None



def _coerce_str(value: Any) -> str | None:
    """把 metadata 中的展示字段安全转为非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None



def _find_latest_session_run(
    session: AgnoSessionDetail,
    *,
    agent_id: str,
    statuses: set[RunStatus] | None = None,
) -> RunOutput | TeamRunOutput | None:
    """按创建时间倒序查找当前 Agent/Team 的最近 run，可选限制状态集合。"""

    candidates: list[tuple[int, int, RunOutput | TeamRunOutput]] = []
    for index, run in enumerate(session.runs or []):
        owner_id = _resolve_run_owner_id(run)
        if owner_id is not None and str(owner_id) != agent_id:
            continue
        run_status = _coerce_run_status(getattr(run, "status", None))
        if statuses is not None and run_status not in statuses:
            continue
        created_at = getattr(run, "created_at", None)
        try:
            created_order = int(created_at)
        except (TypeError, ValueError):
            created_order = index
        candidates.append((created_order, index, run))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]



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



def _run_latest_event_index(run: RunOutput | TeamRunOutput) -> int:
    """按 Agno run.events 计算当前可回放的最后事件下标。"""

    events = getattr(run, "events", None) or []
    return len(events) - 1



def _run_latest_event_index_from_detail(detail: AgnoSessionDetail | Any, run_id: str | None) -> int:
    """从会话详情读取指定 run 已持久化的最后事件下标。"""

    if not run_id or not isinstance(detail, (AgentSession, TeamSession)):
        return -1
    run = detail.get_run(run_id)
    return _run_latest_event_index(run) if run is not None else -1



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



def _resolve_session_owner_id(payload: AgnoSessionDetail) -> str | None:
    """提取 Agno session 所属的 Agent/Team ID。"""

    owner_id = getattr(payload, "agent_id", None) or getattr(payload, "team_id", None)
    if not owner_id:
        agent_data = getattr(payload, "agent_data", None)
        team_data = getattr(payload, "team_data", None)
        if isinstance(agent_data, dict):
            owner_id = agent_data.get("agent_id")
        if not owner_id and isinstance(team_data, dict):
            owner_id = team_data.get("agent_id") or team_data.get("team_id")
    return str(owner_id) if owner_id else None



def _resolve_run_owner_id(payload: RunOutput | TeamRunOutput | Any) -> str | None:
    """提取 Agno run 所属的 Agent/Team ID。"""

    owner_id = getattr(payload, "agent_id", None) or getattr(payload, "team_id", None)
    return str(owner_id) if owner_id else None



def _prepare_team_run_output_for_agno_continue(
    run: RunOutput | TeamRunOutput | None,
    *,
    agent_id: str,
    agent_name: str | None,
) -> TeamRunOutput | None:
    """补齐 Agno Team continue 复用 Agent 工具事件 helper 所需的兼容字段。"""

    if not isinstance(run, TeamRunOutput):
        return None

    if not run.team_id:
        run.team_id = agent_id
    if not run.team_name:
        run.team_name = agent_name or agent_id
    setattr(run, "agent_id", str(run.team_id or agent_id))
    setattr(run, "agent_name", str(run.team_name or agent_name or agent_id))

    for member_run in run.member_responses or []:
        if isinstance(member_run, TeamRunOutput):
            _prepare_team_run_output_for_agno_continue(
                member_run,
                agent_id=str(member_run.team_id or agent_id),
                agent_name=str(member_run.team_name or agent_name or agent_id),
            )
    return run



def _resolve_message_run_id(payload: Any) -> str:
    """从 Agno 消息中尽量提取所属 run_id，用于把图片附件挂回用户消息。"""

    for field_name in ("run_id", "runId"):
        value = getattr(payload, field_name, None)
        if value:
            return str(value)
    metadata = getattr(payload, "metadata", None)
    if isinstance(metadata, dict):
        for field_name in ("run_id", "runId"):
            value = metadata.get(field_name)
            if value:
                return str(value)
    return ""



def _normalize_message_tool_calls(payload: Any) -> list[dict[str, Any]]:
    """把 Agno assistant.tool_calls 透传为 Editor 可消费的 JSON 列表。"""

    encoded = jsonable_encoder(getattr(payload, "tool_calls", None) or [])
    if not isinstance(encoded, list):
        return []
    return [item for item in encoded if isinstance(item, dict)]



def _extract_tool_error_info(
    *,
    payload: dict[str, Any],
    tool_execution: dict[str, Any],
) -> tuple[str | None, str | None, bool, bool, str | None]:
    """从 ToolCallError 事件中提取可稳定下发给前端的错误文案与错误码。"""

    candidates = [
        payload.get("error"),
        tool_execution.get("error"),
        payload.get("content"),
        tool_execution.get("result"),
    ]

    resolved_message: str | None = None
    resolved_code: str | None = None
    repair_attempted = False
    repair_succeeded = False
    repair_reason: str | None = None
    for candidate in candidates:
        candidate = _normalize_error_payload(candidate)
        candidate_message = _extract_error_message(candidate)
        candidate_code = _extract_error_code(candidate)
        candidate_repair_attempted = _extract_error_flag(candidate, "repair_attempted")
        candidate_repair_succeeded = _extract_error_flag(candidate, "repair_succeeded")
        candidate_repair_reason = _extract_error_text_field(candidate, "repair_reason")
        if resolved_message is None and candidate_message:
            resolved_message = candidate_message
        if resolved_code is None and candidate_code:
            resolved_code = candidate_code
        if candidate_repair_attempted is not None:
            repair_attempted = candidate_repair_attempted
        if candidate_repair_succeeded is not None:
            repair_succeeded = candidate_repair_succeeded
        if repair_reason is None and candidate_repair_reason:
            repair_reason = candidate_repair_reason
        if resolved_message and resolved_code and repair_reason is not None:
            break

    return resolved_message, resolved_code, repair_attempted, repair_succeeded, repair_reason



def _normalize_error_payload(value: Any) -> Any:
    """将 JSON 字符串错误体反序列化为字典，便于统一提取结构化字段。"""

    if not isinstance(value, str):
        return value

    stripped_value = value.strip()
    if not stripped_value.startswith("{"):
        return value

    try:
        parsed_value = json.loads(stripped_value)
    except json.JSONDecodeError:
        return value

    return parsed_value if isinstance(parsed_value, dict) else value



def _extract_error_message(value: Any) -> str | None:
    """把多种错误载荷统一折叠为用户可读的字符串。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("detail", "message", "error", "content"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return _stringify_content(value)



def _extract_error_code(value: Any) -> str | None:
    """尽量从错误载荷中提取结构化错误码。"""

    if not isinstance(value, dict):
        return None
    for key in ("code", "error_code"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None



def _extract_error_flag(value: Any, field_name: str) -> bool | None:
    """提取错误载荷中的布尔标记字段。"""

    if not isinstance(value, dict):
        return None
    candidate = value.get(field_name)
    return candidate if isinstance(candidate, bool) else None



def _extract_error_text_field(value: Any, field_name: str) -> str | None:
    """提取错误载荷中的文本字段。"""

    if not isinstance(value, dict):
        return None
    candidate = value.get(field_name)
    if isinstance(candidate, str) and candidate.strip():
        return candidate
    return None



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



def _active_run_payload(run: RunOutput | TeamRunOutput) -> dict[str, Any]:
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



def _normalize_raw_event_payload(raw_event: Any) -> dict[str, Any]:
    """把 Agno 原始事件归一成字典，供检查点识别和临时历史估算使用。"""

    payload = _event_payload(raw_event)
    return payload if isinstance(payload, dict) else {}



def _raw_event_name(raw_event: Any, payload: dict[str, Any]) -> str:
    """读取 Agno 原始事件名，兼容 dict 与事件对象两种形态。"""

    return str(payload.get("event") or type(raw_event).__name__)



def _raw_event_text_content(payload: dict[str, Any]) -> str | None:
    """从内容完成事件中提取最终文本，作为缺失 delta 时的兜底。"""

    member_event_data = _extract_member_event_data(payload)
    if member_event_data.get("parent_run_id") and member_event_data.get("member_run_id"):
        return None
    content, _ = _split_reasoning_content(
        _extract_text_content(payload.get("content")),
        _resolve_reasoning_content(payload),
    )
    return content
