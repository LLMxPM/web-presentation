"""文件功能：封装 Agent 会话 Facade 的 scope、session 类型与历史消息读取辅助逻辑。"""

from __future__ import annotations

from typing import Any

from agno.db.base import SessionType
from agno.run.base import RunStatus
from agno.session.agent import AgentSession
from agno.session.team import TeamSession

from app.ai.session_facade_common import (
    AgnoSessionDetail,
    _coerce_int,
    _coerce_run_status,
    _coerce_str,
    _resolve_run_owner_id,
    _stringify_content,
)
from app.ai.session_facade_models import _SessionMessageRecord, _TempHistoryMessage
from app.schemas.agent import AgentScopeContext

_AGNO_CONTEXT_NOTE_PREFIX = "Take note of the following content"


def _scope_from_metadata(metadata: dict[str, Any]) -> AgentScopeContext | None:
    """从会话或 run metadata 中恢复业务 scope，兼容旧会话缺少 scope_type 的数据。"""

    workspace_id = _coerce_int(metadata.get("workspace_id"))
    if workspace_id is None:
        return None
    project_id = _coerce_int(metadata.get("project_id"))
    page_id = _coerce_int(metadata.get("page_id"))
    component_id = _coerce_int(metadata.get("component_id"))
    raw_scope_type = str(metadata.get("scope_type") or "").strip()
    scope_type = raw_scope_type if raw_scope_type in {"workspace", "project", "page", "component"} else ""
    if not scope_type:
        if page_id is not None:
            scope_type = "page"
        elif component_id is not None:
            scope_type = "component"
        elif project_id is not None:
            scope_type = "project"
        else:
            scope_type = "workspace"
    return AgentScopeContext(
        scope_type=scope_type,  # type: ignore[arg-type]
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=component_id,
        workspace_name=_coerce_str(metadata.get("workspace_name")),
        project_name=_coerce_str(metadata.get("project_name")),
        page_title=_coerce_str(metadata.get("page_title")),
        component_name=_coerce_str(metadata.get("component_name")),
        source=str(metadata.get("source") or "editor-agent-sidebar"),
    )



def _session_type_for_descriptor(descriptor: Any) -> SessionType:
    """根据目录 entry_kind 选择 Agno 会话类型。"""

    return SessionType.TEAM if getattr(descriptor, "entry_kind", None) == "team" else SessionType.AGENT



def _session_type_for_detail(detail: AgnoSessionDetail) -> SessionType:
    """根据 Agno session 实例选择写回类型。"""

    return SessionType.TEAM if isinstance(detail, TeamSession) else SessionType.AGENT



def _session_type_candidates(primary: SessionType) -> tuple[SessionType, ...]:
    """返回读取会话时的主类型和兼容类型。"""

    if primary == SessionType.TEAM:
        return (SessionType.TEAM, SessionType.AGENT)
    return (primary,)



def _get_session_messages(session_detail: AgnoSessionDetail, *, agent_id: str, **kwargs: Any) -> list[Any]:
    """按 Agno session 类型读取消息，Team 默认隐藏成员内部消息。"""

    if isinstance(session_detail, TeamSession):
        return list(session_detail.get_messages(team_id=agent_id, skip_member_messages=True, **kwargs))
    return list(session_detail.get_messages(agent_id=agent_id, **kwargs))



def _merge_history_messages_for_policy(persisted_messages: list[Any], extra_messages: list[Any]) -> list[Any]:
    """合并已持久化历史和当前 run 临时历史，避免同一消息重复计入预算。"""

    result = [*persisted_messages]
    seen = {_history_message_identity(message) for message in persisted_messages}
    for message in extra_messages:
        identity = _history_message_identity(message)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(message)
    return result



def _history_message_identity(message: Any) -> tuple[str, str, str | None, str | None]:
    """提取消息去重标识；内容会序列化以兼容工具 JSON 结果。"""

    return (
        str(getattr(message, "role", "") or "").lower(),
        _stringify_content(getattr(message, "content", None)),
        _coerce_str(getattr(message, "tool_name", None)),
        _coerce_str(getattr(message, "tool_call_id", None)),
    )



def _get_session_message_records(session_detail: AgnoSessionDetail, *, agent_id: str, **kwargs: Any) -> list[_SessionMessageRecord]:
    """按 run 展开消息并保留 run_id，弥补 Agno get_messages 丢失外层 run 信息的问题。"""

    skip_statuses = kwargs.get("skip_statuses")
    if skip_statuses is None:
        skip_statuses = [RunStatus.paused, RunStatus.cancelled, RunStatus.error]
    skip_history_messages = bool(kwargs.get("skip_history_messages", True))
    records: list[_SessionMessageRecord] = []
    for run in session_detail.runs or []:
        owner_id = _resolve_run_owner_id(run)
        if owner_id is not None and str(owner_id) != agent_id:
            continue
        if getattr(run, "parent_run_id", None) is not None:
            continue
        if _coerce_run_status(getattr(run, "status", None)) in skip_statuses:
            continue
        run_id = _coerce_str(getattr(run, "run_id", None))
        for message in getattr(run, "messages", None) or []:
            if skip_history_messages and getattr(message, "from_history", False):
                continue
            records.append(_SessionMessageRecord(run_id=run_id, message=message))
    return records



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



def _session_metadata(payload: Any) -> dict[str, Any]:
    """从 Agno session 或测试替身中读取 metadata。"""

    if isinstance(payload, dict):
        metadata = payload.get("metadata")
    else:
        metadata = getattr(payload, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}



def _build_continue_temp_history_messages(tool_execution: dict[str, Any]) -> list[_TempHistoryMessage]:
    """把继续 paused run 的用户决策临时视作工具结果参与上下文估算。"""

    if not tool_execution:
        return []
    content = {
        key: value
        for key, value in tool_execution.items()
        if key not in {"tool_args", "tool_call_id"}
    }
    if not content:
        content = tool_execution
    return [
        _TempHistoryMessage(
            role="tool",
            content=content,
            tool_name=_coerce_str(tool_execution.get("tool_name")),
            tool_call_id=_coerce_str(tool_execution.get("tool_call_id")),
            tool_args=tool_execution.get("tool_args"),
        )
    ]



def _dedupe_scopes(scopes: tuple[str, ...]) -> tuple[str, ...]:
    """保持原有顺序去重工具授权 scope。"""

    result: list[str] = []
    for scope in scopes:
        if scope not in result:
            result.append(scope)
    return tuple(result)
