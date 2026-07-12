"""文件功能：验证成员助手委派的消息恢复、异常收敛与父运行停止传播。"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai.member_delegation import (
    _MemberAgentRunner,
    _build_member_history_processors,
    _merge_member_message_history,
)
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentMemberRun, AiAgentRun


class _FakeContextProcessor:
    """模拟上下文处理器，确保成员侧包装函数按单参数 messages 调用也能工作。"""

    def __init__(self) -> None:
        """初始化记录字段，用于断言包装函数传入的参数。"""

        self.seen_run_context: Any | None = None
        self.seen_messages: list[Any] | None = None

    async def process(self, run_context: Any | None, messages: list[Any]) -> list[Any]:
        """记录调用参数并原样返回消息列表。"""

        self.seen_run_context = run_context
        self.seen_messages = messages
        return messages


class _FailureRecoverySession:
    """模拟异常事务，验证 rollback/reload 必须发生在缓冲事件 flush 之前。"""

    def __init__(self, parent_run: Any, member_run: Any) -> None:
        """保存重载结果，并记录数据库动作顺序。"""

        self.parent_run = parent_run
        self.member_run = member_run
        self.failed = True
        self.actions: list[str] = []

    async def rollback(self) -> None:
        """恢复事务可用状态。"""

        self.actions.append("rollback")
        self.failed = False

    async def get(self, model: Any, identity: str, *, populate_existing: bool = False) -> Any:
        """返回重新加载的父运行或成员运行。"""

        assert populate_existing is True
        assert not self.failed
        if model is AiAgentRun:
            self.actions.append("get_parent")
            assert identity == self.parent_run.run_id
            return self.parent_run
        if model is AiAgentMemberRun:
            self.actions.append("get_member")
            assert identity == self.member_run.member_run_id
            return self.member_run
        raise AssertionError(f"unexpected model: {model}")

    async def refresh(self, instance: Any, *, attribute_names: list[str]) -> None:
        """记录父运行控制状态刷新，并拒绝在失败事务上执行。"""

        _ = instance, attribute_names
        assert not self.failed
        self.actions.append("refresh_parent")


class _FailureProjector:
    """模拟尽力 flush 再次破坏事务的投影器。"""

    def __init__(self, session: _FailureRecoverySession) -> None:
        """保存事务对象以验证调用顺序。"""

        self.session = session

    async def flush_delta_buffer(self, *, best_effort: bool = False) -> list[Any]:
        """确认首次 rollback 已完成，并模拟 flush 后事务再次失效。"""

        assert best_effort is True
        assert not self.session.failed
        assert self.session.actions[:3] == ["rollback", "get_parent", "get_member"]
        self.session.actions.append("flush")
        self.session.failed = True
        return []


class _ParentControlSession:
    """模拟父运行状态刷新与成员取消提交。"""

    def __init__(self) -> None:
        """初始化调用计数。"""

        self.refresh_count = 0
        self.commit_count = 0

    async def refresh(self, instance: Any, *, attribute_names: list[str]) -> None:
        """记录控制状态刷新。"""

        _ = instance, attribute_names
        self.refresh_count += 1

    async def commit(self) -> None:
        """记录不追加父事件时的直接状态提交。"""

        self.commit_count += 1


def _build_test_runner(*, session: Any, parent_run: Any, member_run: Any) -> _MemberAgentRunner:
    """构造只包含生命周期测试所需字段的成员 runner。"""

    runner = object.__new__(_MemberAgentRunner)
    runner._session = session
    runner._session_factory = SimpleNamespace()
    runner._current = SimpleNamespace(user=SimpleNamespace(id=1))
    runner._scope = SimpleNamespace()
    runner._runtime_context = SimpleNamespace()
    runner._parent_run = parent_run
    runner._member_run = member_run
    runner._parent_run_id = parent_run.run_id
    runner._parent_session_id = parent_run.session_id
    runner._member_run_id = member_run.member_run_id
    runner._member_agent_id = member_run.agent_id
    runner._store = SimpleNamespace()
    return runner


def test_merge_member_message_history_should_filter_invalid_items() -> None:
    """成员消息历史合并应过滤非 dict 项，避免恢复运行时坏数据触发异常。"""

    base = [{"kind": "request", "parts": []}, "invalid"]  # type: ignore[list-item]
    latest = [{"kind": "request", "parts": []}, {"kind": "response", "parts": []}]

    assert _merge_member_message_history(base, latest) == latest


def test_merge_member_message_history_should_append_when_latest_not_prefix() -> None:
    """新消息不是完整快照时，应追加到既有成员历史后。"""

    base = [{"kind": "request", "parts": []}]
    latest = [{"kind": "response", "parts": []}]

    assert _merge_member_message_history(base, latest) == [*base, *latest]


@pytest.mark.asyncio
async def test_build_member_history_processors_should_accept_messages_only() -> None:
    """成员历史处理器应适配 Pydantic AI 1.38 的单参数调用方式。"""

    context_processor = _FakeContextProcessor()
    messages = [{"kind": "request", "parts": []}]

    history_processor = _build_member_history_processors(context_processor)[0]  # type: ignore[arg-type]

    assert await history_processor(messages) == messages
    assert context_processor.seen_run_context is None
    assert context_processor.seen_messages is messages


@pytest.mark.asyncio
async def test_failure_recovery_should_rollback_before_and_after_best_effort_flush() -> None:
    """异常事务应先 rollback/reload；尽力 flush 后还要再次恢复，避免 PendingRollbackError。"""

    parent_run = SimpleNamespace(
        run_id="parent-run-recovery",
        session_id="session-recovery",
        status="running",
        cancel_requested_at=None,
    )
    member_run = SimpleNamespace(
        member_run_id="member-run-recovery",
        agent_id="resource-manager",
    )
    session = _FailureRecoverySession(parent_run, member_run)
    runner = _build_test_runner(session=session, parent_run=parent_run, member_run=member_run)

    await runner._prepare_failure_recovery(_FailureProjector(session))  # type: ignore[arg-type]

    assert session.actions == [
        "rollback",
        "get_parent",
        "get_member",
        "refresh_parent",
        "flush",
        "rollback",
        "get_parent",
        "get_member",
        "refresh_parent",
    ]
    assert session.failed is False
    assert runner._parent_run is parent_run
    assert runner._member_run is member_run


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parent_status", "cancel_requested_at", "should_emit_cancel_event"),
    [
        ("failed", None, False),
        ("cancelled", None, False),
        ("completed", None, False),
        ("cancelling", None, True),
        ("running", datetime.now(tz=UTC), True),
    ],
)
async def test_parent_stop_state_should_cancel_member_without_late_terminal_event(
    monkeypatch: pytest.MonkeyPatch,
    parent_status: str,
    cancel_requested_at: datetime | None,
    should_emit_cancel_event: bool,
) -> None:
    """父运行停止时成员应取消；父已终态时不得再追加 member.run.cancelled。"""

    parent_run = SimpleNamespace(
        run_id=f"parent-run-{parent_status}",
        session_id="session-parent-stop",
        status=parent_status,
        cancel_requested_at=cancel_requested_at,
    )
    member_run = SimpleNamespace(
        member_run_id=f"member-run-{parent_status}",
        agent_id="resource-manager",
        status="running",
        pending_requirement_json={"id": "pending-member-requirement"},
        finished_at=None,
        updated_at=None,
    )
    session = _ParentControlSession()
    runner = _build_test_runner(session=session, parent_run=parent_run, member_run=member_run)
    emitted_events: list[str] = []
    tool_failure_options: list[tuple[bool, str]] = []

    async def reload_runs(*, require_member: bool = True) -> bool:
        """保持当前轻量对象，模拟 rollback/reload 已成功。"""

        assert require_member is False
        return True

    async def mark_running_tools_failed(*, message: str, emit_events: bool = True) -> None:
        """记录成员工具是否允许发出错误事件。"""

        tool_failure_options.append((emit_events, message))

    async def append_member_event(event_suffix: str, **_: Any) -> Any:
        """记录取消事件，避免依赖真实运行态 store。"""

        emitted_events.append(event_suffix)
        return SimpleNamespace(event=f"member.{event_suffix}")

    monkeypatch.setattr(runner, "_rollback_and_reload_runs", reload_runs)
    monkeypatch.setattr(runner, "_mark_running_member_tools_failed", mark_running_tools_failed)
    monkeypatch.setattr(runner, "append_member_event", append_member_event)

    with pytest.raises(AppException) as exc_info:
        await runner._raise_if_parent_cancelled()

    assert exc_info.value.code == "AI_RUN_CANCELLED"
    assert member_run.status == "cancelled"
    assert member_run.pending_requirement_json is None
    assert member_run.finished_at is not None
    assert tool_failure_options[0][0] == (parent_status not in {"failed", "cancelled", "completed"})
    assert emitted_events == (["run.cancelled"] if should_emit_cancel_event else [])
    assert session.commit_count == (0 if should_emit_cancel_event else 1)
