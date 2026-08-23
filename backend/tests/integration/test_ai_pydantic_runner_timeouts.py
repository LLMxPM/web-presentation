"""文件功能：验证 Pydantic Agent 模型流与工具流使用彼此独立的空闲超时。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from httpx import AsyncClient
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.tools import Tool
import pytest

from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.pydantic_runner import PydanticAgentRunner
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from tests.integration.test_ai_pydantic_runner_smoke import (
    _collect_runner_events,
    _create_workspace_session,
    _latest_tool_return,
    _runtime_context,
)


async def test_pydantic_runner_should_timeout_when_model_stream_entry_hangs() -> None:
    """模型流上下文迟迟无法进入时，应取消入口等待并返回既有超时错误。"""

    cancelled = False

    class HangingStreamContext:
        """模拟供应商一直不返回响应头的模型流上下文。"""

        async def __aenter__(self) -> object:
            nonlocal cancelled
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled = True
                raise

        async def __aexit__(self, *_args: Any) -> bool:
            return False

    runner = PydanticAgentRunner(object(), stream_idle_timeout_seconds=0.02)

    with pytest.raises(AppException) as exc_info:
        async with runner._model_stream_with_entry_timeout(HangingStreamContext()):
            raise AssertionError("模型流入口不应成功返回。")

    assert exc_info.value.code == "AI_AGENT_STREAM_IDLE_TIMEOUT"
    assert cancelled


async def test_pydantic_runner_should_allow_tool_stream_to_exceed_model_idle_timeout(
    authenticated_client: AsyncClient,
) -> None:
    """工具等待超过模型流阈值但未超过工具流阈值时，父 run 应继续完成。"""

    async def stream_function(messages: list[Any], info: AgentInfo) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """首次请求慢工具，收到工具结果后输出最终答复。"""

        _ = info
        if _latest_tool_return(messages) is not None:
            yield "慢工具已完成。"
            return
        yield {
            0: DeltaToolCall(
                name="slow_tool",
                json_args="{}",
                tool_call_id="tool-slow-within-tool-timeout",
            )
        }

    async def slow_tool() -> str:
        """模拟耗时超过模型流空闲阈值的成员委派类工具。"""

        await asyncio.sleep(0.08)
        return "工具结果"

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner 独立工具超时工作空间",
        session_name="Pydantic Runner 独立工具超时会话",
    )
    model = FunctionModel(stream_function=stream_function)

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id="pydantic-runner-tool-timeout-separated",
            message="调用慢工具。",
            image_attachment_ids=[],
        )
        events = await _collect_runner_events(
            PydanticAgentRunner(
                store,
                stream_idle_timeout_seconds=0.02,
                tool_stream_idle_timeout_seconds=0.2,
            ).stream_run(
                run_model=run_start.run_model,
                agent_id="agent-coordinator",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="调用慢工具。",
                tools=[Tool(slow_tool, name="slow_tool")],
            )
        )
        completed_run = await store.get_latest_run_model(session_id=session_id, agent_id="agent-coordinator")

    assert completed_run is not None
    assert completed_run.status == "completed"
    assert completed_run.content == "慢工具已完成。"
    assert [event.event for event in events].count("tool.completed") == 1
    assert events[-1].event == "run.completed"




async def test_pydantic_runner_should_fail_when_tool_stream_exceeds_own_idle_timeout(
    authenticated_client: AsyncClient,
) -> None:
    """工具等待超过独立工具流阈值时，父 run 仍应收敛为空闲超时失败。"""

    async def stream_function(messages: list[Any], info: AgentInfo) -> AsyncIterator[dict[int, DeltaToolCall]]:
        """请求一个会超过工具流阈值的慢工具。"""

        _ = messages, info
        yield {
            0: DeltaToolCall(
                name="timeout_tool",
                json_args="{}",
                tool_call_id="tool-exceeds-tool-timeout",
            )
        }

    async def timeout_tool() -> str:
        """模拟超过独立工具流空闲阈值后才返回。"""

        await asyncio.sleep(0.1)
        return "迟到的工具结果"

    _, session_id, scope = await _create_workspace_session(
        authenticated_client,
        workspace_name="Pydantic Runner 工具流超时工作空间",
        session_name="Pydantic Runner 工具流超时会话",
    )
    model = FunctionModel(stream_function=stream_function)

    async with get_session_factory()() as db_session:
        store = PlatformAgentRuntimeStore(db_session, user_id=1)
        run_start = await store.start_run(
            session_id=session_id,
            agent_id="agent-coordinator",
            scope=scope,
            run_id="pydantic-runner-tool-idle-timeout",
            message="调用超时工具。",
            image_attachment_ids=[],
        )
        events = await _collect_runner_events(
            PydanticAgentRunner(
                store,
                stream_idle_timeout_seconds=0.2,
                tool_stream_idle_timeout_seconds=0.02,
            ).stream_run(
                run_model=run_start.run_model,
                agent_id="agent-coordinator",
                model=model,
                model_settings={},
                runtime_context=_runtime_context(scope),
                message="调用超时工具。",
                tools=[Tool(timeout_tool, name="timeout_tool")],
            )
        )
        failed_run = await store.get_latest_run_model(session_id=session_id, agent_id="agent-coordinator")
        await asyncio.sleep(0.11)

    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.error_code == "AI_AGENT_STREAM_IDLE_TIMEOUT"
    assert events[-1].event == "run.error"
