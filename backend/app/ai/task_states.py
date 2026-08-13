"""文件功能：集中定义智能体运行、成员、工具、Requirement 与外部任务状态契约。"""

from __future__ import annotations

from collections.abc import Mapping


RUN_ACTIVE_STATUSES = frozenset({"running", "paused", "waiting_external", "cancelling"})
RUN_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})
MEMBER_ACTIVE_STATUSES = frozenset({"running", "waiting_external"})
MEMBER_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})
TOOL_ACTIVE_STATUSES = frozenset({"running", "waiting_external"})
TOOL_TERMINAL_STATUSES = frozenset({"completed", "error", "cancelled", "interrupted"})
REQUIREMENT_ACTIVE_STATUSES = frozenset({"pending", "resolving"})
REQUIREMENT_TERMINAL_STATUSES = frozenset({"resolved", "cancelled", "failed"})
EXTERNAL_BATCH_ACTIVE_STATUSES = frozenset({"collecting", "waiting_tasks", "ready", "resuming"})
EXTERNAL_BATCH_TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})
EXTERNAL_TASK_ACTIVE_STATUSES = frozenset({"pending", "running", "waiting_provider"})
EXTERNAL_TASK_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

RUN_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "running": frozenset({"paused", "waiting_external", "cancelling", "completed", "cancelled", "failed"}),
    "paused": frozenset({"running", "cancelling", "cancelled", "failed"}),
    "waiting_external": frozenset({"running", "cancelling", "cancelled", "failed"}),
    "cancelling": frozenset({"cancelled", "failed"}),
}
MEMBER_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "running": frozenset({"waiting_external", "completed", "cancelled", "failed"}),
    "waiting_external": frozenset({"running", "cancelled", "failed"}),
}
TOOL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "running": frozenset({"waiting_external", "completed", "error", "cancelled", "interrupted"}),
    "waiting_external": frozenset({"completed", "error", "cancelled", "interrupted"}),
}
REQUIREMENT_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pending": frozenset({"resolving", "resolved", "cancelled", "failed"}),
    "resolving": frozenset({"pending", "resolved", "cancelled", "failed"}),
}
EXTERNAL_BATCH_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "collecting": frozenset({"waiting_tasks", "cancelled", "failed"}),
    "waiting_tasks": frozenset({"ready", "cancelled", "failed"}),
    "ready": frozenset({"resuming", "cancelled", "failed"}),
    "resuming": frozenset({"ready", "completed", "cancelled", "failed"}),
}
EXTERNAL_TASK_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset({"pending", "waiting_provider", "succeeded", "failed", "cancelled"}),
    "waiting_provider": frozenset({"pending", "succeeded", "failed", "cancelled"}),
}


def ensure_state_transition(*, current: str, target: str, transitions: Mapping[str, frozenset[str]], entity: str) -> None:
    """校验状态迁移是否合法；相同状态作为幂等操作放行。"""

    if current == target:
        return
    if target not in transitions.get(current, frozenset()):
        raise ValueError(f"AI_STATE_TRANSITION_INVALID:{entity}:{current}->{target}")
