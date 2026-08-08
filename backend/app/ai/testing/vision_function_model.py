"""文件功能：构造图片理解 E2E FunctionModel，只产出符合业务 Schema 的确定性结构化输出。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.ai.testing.scenario_protocol import VISION_MODEL_ROLE, MockScenarioError

VISION_MOCK_DESCRIPTION = "E2E mock 图片理解：纯色底上的示例插图，构图简洁，适合作为横向配图。"
VISION_MOCK_SUMMARY = "共收到 {count} 张图片，均为 E2E mock 确定性描述。"


def build_vision_function_model(model_id: str) -> FunctionModel:
    """构造图片理解 mock 模型；图片理解走非流式 run，但同时提供流式入口兜底。"""

    def function(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
        """非流式入口：按输入图片数量返回结构化理解结果。"""

        return _respond(messages, agent_info)

    async def stream_function(
        messages: list[ModelMessage], agent_info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """流式入口：把同一个确定性响应投影为工具调用增量或文本增量。"""

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
    """统计本次输入图片数量，构造符合 ImageUnderstandingOutput 的确定性结果。"""

    image_count = _count_input_images(messages)
    if image_count <= 0:
        raise MockScenarioError(
            scenario_id="e2e-vision-single-call",
            model_role=VISION_MODEL_ROLE,
            detail="图片理解 mock 未在本次请求中收到任何图片输入。",
        )
    output = _build_output(image_count)
    output_mode = str(getattr(agent_info.model_request_parameters, "output_mode", "tool"))
    if output_mode == "tool" and agent_info.output_tools:
        output_tool = agent_info.output_tools[0]
        return ModelResponse(
            parts=[ToolCallPart(output_tool.name, output, tool_call_id="e2e-mock-vision-output")]
        )
    return ModelResponse(parts=[TextPart(json.dumps(output, ensure_ascii=False))])


def _count_input_images(messages: list[ModelMessage]) -> int:
    """统计最近一次用户请求中的 BinaryContent 数量，作为输入图片数。"""

    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, UserPromptPart):
                content = part.content
                if isinstance(content, list):
                    return sum(1 for item in content if isinstance(item, BinaryContent))
                return 0
    return 0


def _build_output(image_count: int) -> dict[str, Any]:
    """构造按 input_index 0..n-1 排列的确定性理解结果。"""

    return {
        "summary": VISION_MOCK_SUMMARY.format(count=image_count),
        "items": [
            {
                "input_index": index,
                "description": VISION_MOCK_DESCRIPTION,
                "ocr_text": None,
                "dimensions": {"width": None, "height": None},
                "aspect_ratio": None,
                "colors": ["#2563EB"],
                "layout": "horizontal",
                "findings": [],
                "warnings": [],
            }
            for index in range(image_count)
        ],
        "comparison": None,
    }
