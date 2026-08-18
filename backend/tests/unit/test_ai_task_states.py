"""文件功能：验证智能体统一状态机的合法迁移、终态集合与非法迁移保护。"""

import pytest

from app.ai.task_states import (
    EXTERNAL_BATCH_TRANSITIONS,
    EXTERNAL_TASK_TRANSITIONS,
    REQUIREMENT_TRANSITIONS,
    RUN_TRANSITIONS,
    TOOL_TRANSITIONS,
    ensure_state_transition,
)


@pytest.mark.parametrize(
    ("transitions", "current", "target"),
    [
        (RUN_TRANSITIONS, "running", "waiting_external"),
        (RUN_TRANSITIONS, "waiting_external", "running"),
        (TOOL_TRANSITIONS, "running", "waiting_external"),
        (REQUIREMENT_TRANSITIONS, "pending", "resolving"),
        (REQUIREMENT_TRANSITIONS, "resolving", "pending"),
        (EXTERNAL_BATCH_TRANSITIONS, "ready", "resuming"),
        (EXTERNAL_TASK_TRANSITIONS, "running", "waiting_provider"),
        (EXTERNAL_TASK_TRANSITIONS, "waiting_provider", "pending"),
    ],
)
def test_unified_state_machine_should_allow_declared_transitions(transitions, current: str, target: str) -> None:
    """声明过的迁移应放行。"""

    ensure_state_transition(current=current, target=target, transitions=transitions, entity="test")


@pytest.mark.parametrize(
    ("transitions", "current", "target"),
    [
        (RUN_TRANSITIONS, "completed", "running"),
        (TOOL_TRANSITIONS, "waiting_external", "running"),
        (REQUIREMENT_TRANSITIONS, "resolved", "pending"),
        (EXTERNAL_BATCH_TRANSITIONS, "waiting_tasks", "resuming"),
        (EXTERNAL_TASK_TRANSITIONS, "pending", "succeeded"),
    ],
)
def test_unified_state_machine_should_reject_undeclared_transitions(transitions, current: str, target: str) -> None:
    """未声明迁移必须失败，避免调用方绕过状态机。"""

    with pytest.raises(ValueError, match="AI_STATE_TRANSITION_INVALID"):
        ensure_state_transition(current=current, target=target, transitions=transitions, entity="test")
