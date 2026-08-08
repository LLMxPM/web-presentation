"""文件功能：构造内容助手 E2E FunctionModel，按场景状态机模拟模型决策并支持流式入口。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextContent,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.ai.testing.scenario_protocol import (
    AGENT_MODEL_ROLE,
    MockConversationState,
    MockScenarioError,
    ScenarioToolCall,
)
from app.ai.testing.scenarios import normalize_user_input, select_agent_scenario

COMPRESSED_HISTORY_TEXT = "（E2E mock 历史压缩摘要：本轮对话历史已被压缩。）"
_ATTACHMENT_ID_PATTERN = re.compile(r"attachment_id=(\d+)")


def build_agent_function_model(model_id: str) -> FunctionModel:
    """构造内容助手 mock 模型；同时提供流式与非流式入口，因为平台 runner 走流式。"""

    def function(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
        """非流式入口：直接返回场景状态机推导的完整响应。"""

        return _respond(messages, agent_info)

    async def stream_function(
        messages: list[ModelMessage], agent_info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """流式入口：把同一个确定性响应投影为文本增量或工具调用增量。"""

        response = _respond(messages, agent_info)
        for index, part in enumerate(response.parts):
            if isinstance(part, TextPart):
                yield part.content
            elif isinstance(part, ToolCallPart):
                yield {
                    index: DeltaToolCall(
                        name=part.tool_name,
                        json_args=json.dumps(part.args, ensure_ascii=False),
                        tool_call_id=part.tool_call_id,
                    )
                }

    return FunctionModel(function, stream_function=stream_function, model_name=f"e2e-mock:{model_id}")


def _respond(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
    """按本次收到的消息历史推导响应；不读写任何进程级可变状态。"""

    # 历史压缩器复用同一模型对象但没有工具；用独立的确定性文本兜底，
    # 避免压缩调用误入内容助手状态机。
    if not agent_info.function_tools and agent_info.allow_text_output:
        return ModelResponse(parts=[TextPart(COMPRESSED_HISTORY_TEXT)])

    state = derive_conversation_state(messages)
    if state.has_retry_prompt:
        raise MockScenarioError(
            scenario_id="<retry>",
            model_role=AGENT_MODEL_ROLE,
            detail="消息历史中出现 RetryPrompt，说明此前工具调用未通过真实 Schema 校验。",
            observed_tools=state.called_tool_names(),
            message_kinds=_summarize_message_kinds(messages),
        )
    scenario = select_agent_scenario(normalize_user_input(state.initial_user_input))
    return scenario.next_response(state)


def derive_conversation_state(messages: list[ModelMessage]) -> MockConversationState:
    """从消息历史构造当前用户轮次的状态快照。

    Session 历史可能包含多个已完成用户轮次；每遇到新的 UserPrompt 都重置工具状态，
    后续 deferred 恢复只有 ToolReturn、没有新 UserPrompt，因此仍会沿用本轮输入。
    """

    initial_user_input = ""
    tool_calls: list[ScenarioToolCall] = []
    tool_returns: dict[str, list[Any]] = {}
    has_retry_prompt = False
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    initial_user_input = _extract_prompt_text(part.content)
                    tool_calls = []
                    tool_returns = {}
                    has_retry_prompt = False
                elif isinstance(part, ToolReturnPart):
                    tool_returns.setdefault(part.tool_name, []).append(part.content)
                elif isinstance(part, RetryPromptPart):
                    has_retry_prompt = True
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    tool_calls.append(
                        ScenarioToolCall(
                            tool_name=part.tool_name,
                            tool_call_id=str(part.tool_call_id or ""),
                            args=part.args,
                        )
                    )
    attachment_ids = tuple(
        int(match) for match in _ATTACHMENT_ID_PATTERN.findall(initial_user_input)
    )
    return MockConversationState(
        initial_user_input=initial_user_input,
        attachment_ids=attachment_ids,
        tool_calls=tuple(tool_calls),
        tool_returns={name: tuple(returns) for name, returns in tool_returns.items()},
        has_retry_prompt=has_retry_prompt,
    )


def _extract_prompt_text(content: Any) -> str:
    """把 UserPromptPart 内容归一为纯文本，跳过图片等二进制内容。"""

    if isinstance(content, str):
        return content
    segments: list[str] = []
    for item in content:
        if isinstance(item, str):
            segments.append(item)
        elif isinstance(item, TextContent):
            segments.append(item.content)
        elif isinstance(item, BinaryContent):
            continue
    return "\n".join(segments)


def _summarize_message_kinds(messages: list[ModelMessage]) -> tuple[str, ...]:
    """生成脱敏的消息种类摘要，只包含 part 类型和工具名，不包含用户内容。"""

    kinds: list[str] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    kinds.append("system_prompt")
                elif isinstance(part, UserPromptPart):
                    kinds.append("user_prompt")
                elif isinstance(part, ToolReturnPart):
                    kinds.append(f"tool_return:{part.tool_name}")
                elif isinstance(part, RetryPromptPart):
                    kinds.append(f"retry_prompt:{part.tool_name}")
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    kinds.append("text")
                elif isinstance(part, ToolCallPart):
                    kinds.append(f"tool_call:{part.tool_name}")
    return tuple(dict.fromkeys(kinds))
