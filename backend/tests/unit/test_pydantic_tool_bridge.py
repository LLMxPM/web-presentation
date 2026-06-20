"""文件功能：验证 Pydantic AI 工具装配层对平台工具上下文和返回值的处理。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import DeferredToolRequests, Tool
from pydantic_ai.usage import RequestUsage

from app.core.exceptions import AppException
from app.ai.platform_tools import AgentToolContext, AgentToolResult, agent_tool
from app.ai.pydantic_runner import _requirement_from_deferred, _safe_messages
from app.ai.pydantic_tools import AgentToolDeps, _safe_tool_result, _wrap_platform_tool
from app.ai.session_facade_pydantic import _build_continue_message_history, _build_deferred_results


def test_pydantic_tool_bridge_should_expose_tool_instructions_in_description() -> None:
    """Pydantic Tool 说明应包含平台工具使用提示，确保模型实际可见细则。"""

    @agent_tool(show_result=False)
    def guided_tool(run_context: AgentToolContext, name: str) -> AgentToolResult:
        """读取演示数据。"""

        _ = run_context
        return AgentToolResult(content=name)

    guided_tool.instructions = "必须先确认 name 来自工具结果或用户明确输入。"

    wrapped = _wrap_platform_tool(guided_tool)

    assert wrapped.description == "读取演示数据。\n\n工具使用提示：必须先确认 name 来自工具结果或用户明确输入。"
    assert wrapped.function.__doc__ == wrapped.description


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_should_serialize_namespace_result() -> None:
    """平台工具返回 SimpleNamespace 时，应转成 JSON 安全结构再交给 Pydantic AI。"""

    @agent_tool(show_result=False)
    def namespace_tool(run_context: AgentToolContext) -> SimpleNamespace:
        """返回测试工具常用的对象形态。"""

        _ = run_context
        return SimpleNamespace(ok=True, nested=SimpleNamespace(value=1))

    agent = Agent(
        TestModel(call_tools="all"),
        tools=[_wrap_platform_tool(namespace_tool)],
        deps_type=AgentToolDeps,
    )

    result = await agent.run("调用工具", deps=AgentToolDeps(dependencies={"run_id": "run-1", "session_id": "session-1"}))

    assert "namespace_tool" in str(result.output)


def test_safe_tool_result_should_keep_plain_platform_tool_result_content() -> None:
    """平台工具只有文本内容时应保留为文本，避免污染模型上下文。"""

    assert _safe_tool_result(AgentToolResult(content="页面源码内容")) == "页面源码内容"


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_should_pass_platform_tool_context() -> None:
    """工具包装层应向平台工具传入包含 run/session/dependencies 的上下文。"""

    @agent_tool(show_result=False)
    def read_context_tool(run_context: AgentToolContext, name: str) -> AgentToolResult:
        """读取桥接上下文并返回文本。"""

        return AgentToolResult(content=f"{name}:{run_context.run_id}:{run_context.dependencies['session_id']}")

    async def model_func(messages: object, info: AgentInfo) -> ModelResponse:
        """第一次请求工具，工具返回后结束。"""

        _ = info
        for message in reversed(messages):
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", None) == "tool-return":
                    return ModelResponse(parts=[TextPart(content=str(part.content))], usage=RequestUsage(input_tokens=1, output_tokens=1))
        return ModelResponse(
            parts=[ToolCallPart(tool_name="read_context_tool", args={"name": "demo"}, tool_call_id="tool-1")],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )

    agent = Agent(
        FunctionModel(model_func),
        tools=[_wrap_platform_tool(read_context_tool)],
        deps_type=AgentToolDeps,
    )

    result = await agent.run("调用工具", deps=AgentToolDeps(dependencies={"run_id": "run-1", "session_id": "session-1"}))

    assert result.output == "demo:run-1:session-1"


@pytest.mark.asyncio
async def test_pydantic_tool_bridge_should_return_recoverable_app_exception_to_model() -> None:
    """可恢复业务异常应作为工具返回值交给模型，而不是中断整轮运行。"""

    @agent_tool(show_result=False)
    def read_unsupported_resource(run_context: AgentToolContext) -> dict[str, object]:
        """模拟读取到不可按文本读取的资源。"""

        _ = run_context
        raise AppException(status_code=400, code="ASSET_CONTENT_READ_UNSUPPORTED", detail="该资源不支持内容读取。")

    async def model_func(messages: object, info: AgentInfo) -> ModelResponse:
        """首次请求工具，收到结构化错误后结束。"""

        _ = info
        for message in reversed(messages):
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", None) == "tool-return":
                    content = part.content
                    return ModelResponse(
                        parts=[TextPart(content=content["error"]["code"])],
                        usage=RequestUsage(input_tokens=1, output_tokens=1),
                    )
        return ModelResponse(
            parts=[ToolCallPart(tool_name="read_unsupported_resource", args={}, tool_call_id="tool-1")],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )

    agent = Agent(
        FunctionModel(model_func),
        tools=[_wrap_platform_tool(read_unsupported_resource)],
        deps_type=AgentToolDeps,
    )

    result = await agent.run("读取资源", deps=AgentToolDeps(dependencies={"run_id": "run-1", "session_id": "session-1"}))

    assert result.output == "ASSET_CONTENT_READ_UNSUPPORTED"


def test_deferred_ask_user_should_build_feedback_requirement() -> None:
    """ask_user 的 deferred call 应转成前端可渲染的用户反馈 requirement。"""

    requests = DeferredToolRequests(
        calls=[
            ToolCallPart(
                tool_name="ask_user",
                args={
                    "questions": [
                        {
                            "question": "需要采用哪种布局？",
                            "options": [{"label": "紧凑"}, {"label": "宽松"}],
                        }
                    ]
                },
                tool_call_id="tool-feedback-1",
            )
        ],
        metadata={"tool-feedback-1": {"source": "unit-test"}},
    )

    requirement = _requirement_from_deferred(requests, run_id="run-1", session_id="session-1")

    assert requirement.kind == "user_feedback"
    assert requirement.tool_name == "ask_user"
    assert requirement.user_feedback_schema[0]["question"] == "需要采用哪种布局？"
    assert requirement.tool_execution["requires_user_input"] is True
    assert requirement.tool_execution["deferred_metadata"] == {"tool-feedback-1": {"source": "unit-test"}}


def test_deferred_ask_user_without_question_should_fail_fast() -> None:
    """ask_user 参数没有 question 字段时不应进入前端无法提交的暂停态。"""

    requests = DeferredToolRequests(
        calls=[
            ToolCallPart(
                tool_name="ask_user",
                args={
                    "questions": [
                        {
                            "title": "你想放在哪个位置？",
                            "options": [{"label": "第一页之后"}],
                        }
                    ]
                },
                tool_call_id="tool-feedback-1",
            )
        ],
        metadata={},
    )

    with pytest.raises(AppException) as exc_info:
        _requirement_from_deferred(requests, run_id="run-1", session_id="session-1")

    assert exc_info.value.code == "AI_ASK_USER_SCHEMA_INVALID"


def test_user_feedback_continue_should_return_call_result_without_tool_approval() -> None:
    """继续 ask_user 暂停运行时，应把用户答案作为工具返回值交还给 Pydantic AI。"""

    results = _build_deferred_results(
        requirement_tool_call_id="tool-feedback-1",
        decision="confirm",
        note=None,
        tool_execution={
            "tool_name": "ask_user",
            "tool_args": {
                "questions": [
                    {
                        "question": "需要采用哪种布局？",
                        "options": [{"label": "紧凑"}, {"label": "宽松"}],
                    }
                ]
            },
        },
        feedback_selections=[{"question": "需要采用哪种布局？", "selected_label": "紧凑"}],
    )

    assert results.approvals == {}
    assert results.calls["tool-feedback-1"] == 'User feedback received: [{"question": "需要采用哪种布局？", "selected": ["紧凑"]}]'


def test_user_feedback_continue_should_keep_custom_answer_display_marker() -> None:
    """ask_user 自定义回答应保留用户补充标记，供前端回放时识别为纯答案。"""

    results = _build_deferred_results(
        requirement_tool_call_id="tool-feedback-1",
        decision="confirm",
        note=None,
        tool_execution={
            "tool_name": "ask_user",
            "tool_args": {
                "questions": [
                    {
                        "question": "视觉风格倾向是什么？",
                        "options": [{"label": "极简"}],
                    }
                ]
            },
        },
        feedback_selections=[{"question": "视觉风格倾向是什么？", "selected_label": None, "custom_text": "保留当前图标风格"}],
    )

    assert results.calls["tool-feedback-1"] == (
        'User feedback received: [{"question": "视觉风格倾向是什么？", "selected": ["用户补充：保留当前图标风格"]}]'
    )


@pytest.mark.asyncio
async def test_safe_messages_should_serialize_pydantic_ai_message_history() -> None:
    """Pydantic AI 消息对象不是 Pydantic model，应通过官方 TypeAdapter 序列化。"""

    async def model_func(messages: object, info: AgentInfo) -> ModelResponse:
        """返回简单文本，产生标准 Pydantic AI 历史消息。"""

        _ = messages, info
        return ModelResponse(parts=[TextPart(content="ok")], usage=RequestUsage(input_tokens=1, output_tokens=1))

    result = await Agent(FunctionModel(model_func)).run("hello")

    dumped = _safe_messages(result)

    assert [item["kind"] for item in dumped] == ["request", "response"]
    assert dumped[0]["parts"][0]["part_kind"] == "user-prompt"
    assert dumped[1]["parts"][0]["part_kind"] == "text"


def test_continue_message_history_should_rebuild_minimal_history_when_empty() -> None:
    """历史为空的旧暂停 run 应能用用户输入和 tool call 重建继续上下文。"""

    history = _build_continue_message_history(
        run_model_message_history=[],
        run_input_payload={"message": "请调整路由"},
        run_id="run-1",
        tool_execution={
            "tool_name": "apply_project_route_tree",
            "tool_call_id": "tool-1",
            "tool_args": {"routes": []},
        },
    )

    assert len(history) == 2
    assert history[0].parts[0].content == "请调整路由"
    assert history[1].parts[0].tool_name == "apply_project_route_tree"
    assert history[1].parts[0].tool_call_id == "tool-1"


@pytest.mark.asyncio
async def test_rebuilt_continue_history_should_work_with_deferred_approval() -> None:
    """重建的最小历史应能被 Pydantic AI 用于提交确认结果。"""

    async def approved_tool(x: int) -> str:
        """模拟需要用户确认的写入工具。"""

        return f"tool {x}"

    async def model_func(messages: object, info: AgentInfo) -> ModelResponse:
        """首次请求确认工具，收到工具返回后结束。"""

        _ = info
        for message in reversed(messages):
            for part in getattr(message, "parts", []):
                if getattr(part, "part_kind", None) == "tool-return":
                    return ModelResponse(parts=[TextPart(content=f"done {part.content}")], usage=RequestUsage(input_tokens=1, output_tokens=1))
        return ModelResponse(
            parts=[ToolCallPart(tool_name="approved_tool", args={"x": 1}, tool_call_id="tool-1")],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )

    agent = Agent(
        FunctionModel(model_func),
        tools=[Tool(approved_tool, requires_approval=True)],
        output_type=[str, DeferredToolRequests],
    )
    first = await agent.run("hi")
    assert isinstance(first.output, DeferredToolRequests)
    history = _build_continue_message_history(
        run_model_message_history=[],
        run_input_payload={"message": "hi"},
        run_id="run-1",
        tool_execution={"tool_name": "approved_tool", "tool_call_id": "tool-1", "tool_args": {"x": 1}},
    )
    results = _build_deferred_results(
        requirement_tool_call_id="tool-1",
        decision="confirm",
        note=None,
        tool_execution={"tool_name": "approved_tool"},
        feedback_selections=[],
    )

    second = await agent.run("", message_history=history, deferred_tool_results=results)

    assert second.output == "done tool 1"
