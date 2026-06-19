"""文件功能：从 Agno runs 构造 Agent 会话时间线与 Team 成员运行展示数据。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from agno.run.agent import RunOutput
from agno.run.team import TeamRunOutput

from app.ai.agent import AgentRuntimeContext
from app.ai.session_facade_common import (
    AgnoSessionDetail,
    _coerce_str,
    _normalize_run_status_value,
    _normalize_timestamp,
    _resolve_run_owner_id,
)
from app.ai.session_facade_requirements import _extract_pending_requirement, _pending_requirement_timeline_content
from app.ai.session_timeline import build_timeline_items_from_agno_runs as build_timeline_items_from_runs
from app.schemas.agent import AgentMemberRunItem, AgentTimelineItem


def _build_timeline_items_from_agno_runs(
    detail: AgnoSessionDetail,
    *,
    session_id: str,
    agent_id: str,
    runtime_context: AgentRuntimeContext | None = None,
    target_run_ids: set[str] | None = None,
    include_child_runs: bool = False,
    hide_member_events: bool = True,
) -> list[AgentTimelineItem]:
    """从 Agno runs/messages/events 派生 session-first 时间线。"""

    return build_timeline_items_from_runs(
        detail,
        session_id=session_id,
        agent_id=agent_id,
        runtime_context=runtime_context,
        target_run_ids=target_run_ids,
        include_child_runs=include_child_runs,
        hide_member_events=hide_member_events,
        extract_pending_requirement=_extract_pending_requirement,
        pending_requirement_timeline_content=_pending_requirement_timeline_content,
    )



def _build_member_runs_from_agno_runs(
    detail: AgnoSessionDetail,
    *,
    session_id: str,
    agent_id: str,
    runtime_context: AgentRuntimeContext | None,
    parent_timeline_items: list[AgentTimelineItem],
) -> list[AgentMemberRunItem]:
    """从 Team 父 run 的成员响应中提取可单独展示的子 run。"""

    member_runs: list[AgentMemberRunItem] = []
    seen_run_ids: set[str] = set()
    all_runs = list(getattr(detail, "runs", None) or [])
    for parent_index, parent_run in enumerate(all_runs):
        parent_owner_id = _resolve_run_owner_id(parent_run)
        if parent_owner_id is not None and str(parent_owner_id) != agent_id:
            continue
        if getattr(parent_run, "parent_run_id", None) is not None:
            continue
        parent_run_id = _coerce_str(getattr(parent_run, "run_id", None)) or f"run-{parent_index}"
        for member_run in _iter_member_runs_for_parent(parent_run, all_runs=all_runs):
            member_run_id = _coerce_str(getattr(member_run, "run_id", None))
            if not member_run_id or member_run_id in seen_run_ids:
                continue
            seen_run_ids.add(member_run_id)
            member_agent_id = _resolve_run_owner_id(member_run) or ""
            member_runs.append(
                AgentMemberRunItem(
                    parent_run_id=parent_run_id,
                    run_id=member_run_id,
                    agent_id=str(member_agent_id),
                    agent_name=_resolve_run_owner_name(member_run),
                    status=_normalize_run_status_value(getattr(member_run, "status", None)),  # type: ignore[arg-type]
                    created_at=_normalize_timestamp(getattr(member_run, "created_at", None)),
                    updated_at=_normalize_timestamp(getattr(member_run, "updated_at", None)),
                    delegate_tool_call_id=None,
                    timeline_items=_build_timeline_items_from_agno_runs(
                        SimpleNamespace(runs=[member_run]),
                        session_id=session_id,
                        agent_id=str(member_agent_id),
                        runtime_context=runtime_context,
                        target_run_ids={member_run_id},
                        include_child_runs=True,
                        hide_member_events=False,
                    ),
                )
            )

    _assign_delegate_tool_call_ids(member_runs, parent_timeline_items)
    return sorted(member_runs, key=_member_run_sort_key)



def _iter_member_runs_for_parent(parent_run: RunOutput | TeamRunOutput, *, all_runs: list[Any]) -> list[Any]:
    """读取某个父 run 直接产生的成员 run，兼容 member_responses 与 session.runs 两种存储形态。"""

    parent_run_id = _coerce_str(getattr(parent_run, "run_id", None))
    result: list[Any] = []
    seen_ids: set[str] = set()

    def append_member_run(candidate: Any) -> None:
        candidate_run_id = _coerce_str(getattr(candidate, "run_id", None))
        if not candidate_run_id or candidate_run_id in seen_ids:
            return
        seen_ids.add(candidate_run_id)
        result.append(candidate)

    for member_run in getattr(parent_run, "member_responses", None) or []:
        append_member_run(member_run)
    if parent_run_id:
        for run in all_runs:
            if _coerce_str(getattr(run, "parent_run_id", None)) == parent_run_id:
                append_member_run(run)
    return result



def _assign_delegate_tool_call_ids(member_runs: list[AgentMemberRunItem], parent_timeline_items: list[AgentTimelineItem]) -> None:
    """按成员 id 和时间顺序，把子 run 关联到父时间线中的 delegate 工具调用。"""

    used_member_runs: set[str] = set()
    delegate_items = [
        item
        for item in parent_timeline_items
        if item.kind == "tool"
        and item.tool is not None
        and item.tool.tool_name in {"delegate_task_to_member", "delegate_task_to_members"}
    ]
    delegate_items.sort(key=lambda item: (item.order_index, item.event_index if item.event_index is not None else 10**9, item.id))

    for delegate_item in delegate_items:
        if delegate_item.tool is None:
            continue
        delegate_key = delegate_item.tool.tool_call_id or delegate_item.id
        requested_member_id = _delegate_requested_member_id(delegate_item.tool.input_payload)
        candidates = [
            member_run
            for member_run in member_runs
            if member_run.parent_run_id == delegate_item.run_id
            and member_run.run_id not in used_member_runs
            and (requested_member_id is None or member_run.agent_id == requested_member_id)
        ]
        candidates.sort(key=_member_run_sort_key)
        if not candidates:
            continue
        if delegate_item.tool.tool_name == "delegate_task_to_member":
            candidates = candidates[:1]
        for member_run in candidates:
            member_run.delegate_tool_call_id = delegate_key
            used_member_runs.add(member_run.run_id)



def _delegate_requested_member_id(input_payload: Any) -> str | None:
    """从 delegate_task_to_member 参数中提取目标成员 id。"""

    if not isinstance(input_payload, dict):
        return None
    return _coerce_str(input_payload.get("member_id"))



def _member_run_sort_key(member_run: AgentMemberRunItem) -> tuple[bool, str, int, str]:
    """按创建时间排序子 run；缺失时间时用首个事件序号和 run_id 兜底。"""

    first_event_index = min(
        [item.event_index for item in member_run.timeline_items if item.event_index is not None],
        default=10**9,
    )
    return (member_run.created_at is None, member_run.created_at or "", first_event_index, member_run.run_id)



def _resolve_run_owner_name(payload: RunOutput | TeamRunOutput | Any) -> str | None:
    """提取 Agno run 所属 Agent/Team 展示名。"""

    owner_name = getattr(payload, "agent_name", None) or getattr(payload, "team_name", None)
    return str(owner_name) if owner_name else None
