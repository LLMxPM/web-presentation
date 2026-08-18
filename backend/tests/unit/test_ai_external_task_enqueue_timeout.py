"""文件功能：验证外部任务短入队超时及组件入队事务事件契约。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from app.ai import component_mutation_enqueue, external_task_enqueue_timeout
from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_external_task import AiComponentMutationTask


async def test_external_task_enqueue_timeout_should_return_recoverable_unknown_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入队超过短期限时应停止等待，并要求先查状态而非原样重试。"""

    monkeypatch.setattr(
        external_task_enqueue_timeout,
        "get_settings",
        lambda: SimpleNamespace(ai_external_task_enqueue_timeout_seconds=0.01),
    )

    async def slow_enqueue() -> str:
        """模拟数据库连接或行锁长期没有返回。"""

        await asyncio.sleep(1)
        return "unreachable"

    with pytest.raises(AppException) as exc_info:
        await external_task_enqueue_timeout.wait_for_external_task_enqueue(
            slow_enqueue()
        )

    assert exc_info.value.code == "AI_EXTERNAL_TASK_ENQUEUE_TIMEOUT"
    assert exc_info.value.status_code == 503
    assert exc_info.value.data == {
        "retryable": True,
        "outcome": "unknown",
        "hint": "先查询目标实体的最新状态；确认操作未生效后，再使用最新版本参数重新调用。",
    }


async def test_component_enqueue_should_keep_task_and_progress_event_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """组件Task、领域详情和queued事件应由调用方最后一次提交统一落库。"""

    run = SimpleNamespace(
        run_id="run-component-enqueue",
        session_id="session-component-enqueue",
        user_id=7,
        status="running",
        cancel_requested_at=None,
    )
    task = SimpleNamespace(
        task_id="task-component-enqueue", batch_id="batch-component-enqueue"
    )
    captured: dict[str, Any] = {}

    class FakeSession:
        """记录组件入队对会话的提交次数和新增对象。"""

        def __init__(self) -> None:
            self.commits = 0
            self.added: list[Any] = []

        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def get(self, model: type[Any], _identifier: Any) -> Any:
            if model is AiAgentRun:
                return run
            if model is AiComponentMutationTask:
                return None
            return None

        def add(self, value: Any) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            self.commits += 1

    fake_session = FakeSession()

    class FakeStore:
        """捕获append_event的事务控制参数。"""

        def __init__(self, _session: Any, *, user_id: int) -> None:
            captured["user_id"] = user_id

        async def append_event(
            self, _run: Any, event: Any, *, commit: bool = True
        ) -> Any:
            captured["event"] = event
            captured["event_commit"] = commit
            return event

    async def fake_enqueue_external_task(*_args: Any, **_kwargs: Any) -> Any:
        return task

    monkeypatch.setattr(
        component_mutation_enqueue, "enqueue_external_task", fake_enqueue_external_task
    )
    monkeypatch.setattr("app.ai.platform_runtime.PlatformAgentRuntimeStore", FakeStore)

    result = await component_mutation_enqueue.enqueue_component_mutation(
        lambda: fake_session,  # type: ignore[arg-type]
        run_id=run.run_id,
        session_id=run.session_id,
        tool_call_id="tool-component-enqueue",
        deferred_tool_call_id="tool-component-enqueue",
        operation="apply_component_edits",
        workspace_id=25,
        component_id=89,
        arguments={"edits": []},
    )

    assert result.task_id == task.task_id
    assert captured["event_commit"] is False
    assert captured["event"].event == "tool.progress"
    assert fake_session.commits == 1
    assert len(fake_session.added) == 1
