"""文件功能：验证模型单次响应异常批量工具调用会在执行前整批拒绝。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from httpx import AsyncClient
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.tools import Tool

from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.pydantic_runner import PydanticAgentRunner
from app.db.session import get_session_factory
from tests.integration.test_ai_pydantic_runner_smoke import (
    _collect_runner_events,
    _create_workspace_session,
    _runtime_context,
)


async def test_model_oversized_tool_batch_fails_before_any_tool_runs(
    authenticated_client: AsyncClient,
) -> None:
    """65 个并行工具调用应产生有界错误，不能留下 running 工具或执行副作用。"""

    executed = 0

    def probe() -> str:
        """记录是否越过执行前的整批上限。"""

        nonlocal executed
        executed += 1
        return "ok"

    async def stream_function(
        messages: list[Any],
        info: AgentInfo,
    ) -> AsyncIterator[dict[int, DeltaToolCall]]:
        """模拟供应商在一个模型 step 内返回大量重复工具调用。"""

        _ = messages, info
        yield {
            index: DeltaToolCall(name="probe", json_args="{}", tool_call_id=f"probe-{index}")
            for index in range(65)
        }

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="模型批量工具上限工作空间",
        session_name="模型批量工具上限会话",
    )
    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        started = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id="model-oversized-tool-batch",
            message="触发异常工具批次",
            image_attachment_ids=[],
        )
        events = await _collect_runner_events(
            PydanticAgentRunner(store).stream_run(
                run_model=started.run_model,
                agent_id="agent-coordinator",
                model=FunctionModel(stream_function=stream_function),
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="触发异常工具批次",
                tools=[Tool(probe, name="probe")],
            )
        )
        latest = await store.get_latest_run_model(session_id=session_id, agent_id="agent-coordinator")
        assert latest is not None
        assert latest.status == "failed"
        assert latest.error_code == "AI_MODEL_TOOL_CALL_LIMIT_EXCEEDED"
        assert "65 个工具调用" in (latest.error_message or "")
        assert executed == 0
        assert not any(event.event == "tool.started" for event in events)
