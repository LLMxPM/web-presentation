"""文件功能：E2E mock 基础设施契约测试，覆盖分派矩阵、场景状态机、熔断与业务防护。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.ai.testing.agent_function_model import _respond, build_agent_function_model
from app.ai.testing.dispatch import (
    enforce_mock_model_request_fence,
    resolve_mock_chat_model,
    resolve_mock_image_adapter,
)
from app.ai.testing.image_adapter import FIXED_MOCK_PNG, E2eMockImageGenerationAdapter
from app.ai.testing.scenario_protocol import MockScenarioError
from app.ai.testing.scenarios import HELLO_SCENARIO_INPUT, VISUAL_SCENARIO_INPUT
from app.ai.testing.vision_function_model import _build_output, build_vision_function_model
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.image_generation.contracts import ImageGenerationInput
from app.services.image_generation.registry import get_image_model_spec
from app.services.image_understanding_service import ImageUnderstandingOutput


def _set_ai_test_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """切换 AI_TEST_MODE 并清理配置缓存，测试结束后恢复。"""

    monkeypatch.setenv("AI_TEST_MODE", mode)
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings, "cache_clear", get_settings.cache_clear)
    monkeypatch.setenv("_AI_TEST_MODE_TOUCHED", "1")


@pytest.fixture(autouse=True)
def _restore_settings_cache():
    """每个用例结束后清理配置缓存，避免 AI_TEST_MODE 污染其它用例。"""

    yield
    get_settings.cache_clear()


def _agent_info_with_tools() -> AgentInfo:
    """构造带工具的内容助手 AgentInfo 测试桩。"""

    return AgentInfo(
        function_tools=[SimpleNamespace(name="analyze_visuals")],
        allow_text_output=True,
        output_tools=[],
        model_settings=None,
        model_request_parameters=None,
        instructions=None,
    )


def _mock_chat_config(*, model_id: str, status: str = "active", provider_status: str = "active") -> SimpleNamespace:
    """构造带完整启用状态的模型配置，确保 mock 分派不绕过正常运行边界。"""

    return SimpleNamespace(
        model_id=model_id,
        status=status,
        provider_config=SimpleNamespace(status=provider_status, provider_key="openai"),
    )


def _visual_history(final_result: dict) -> list:
    """构造视觉链路完整消息历史：初始输入、两次工具调用与真实回灌结果。"""

    prompt = f"{VISUAL_SCENARIO_INPUT}\nattachment_id=42; name=ref.png"
    info = _agent_info_with_tools()
    first = _respond([ModelRequest(parts=[UserPromptPart(content=prompt)])], info)
    second = _respond(
        [
            ModelRequest(parts=[UserPromptPart(content=prompt)]),
            first,
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="analyze_visuals",
                        content={"summary": "mock", "items": []},
                        tool_call_id="e2e-mock-call-analyze-visuals",
                    )
                ]
            ),
        ],
        info,
    )
    return [
        ModelRequest(parts=[UserPromptPart(content=prompt)]),
        first,
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="analyze_visuals",
                    content={"summary": "mock", "items": []},
                    tool_call_id="e2e-mock-call-analyze-visuals",
                )
            ]
        ),
        second,
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="generate_image",
                    content=final_result,
                    tool_call_id="e2e-mock-call-generate-image",
                )
            ]
        ),
    ]


class TestDispatchMatrix:
    """覆盖 AI_TEST_MODE 与 model ID 前缀的分派组合。"""

    def test_disabled_mode_should_not_inject_mock_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """disabled 模式下 e2e-mock-* 也不注入测试模型或适配器。"""

        _set_ai_test_mode(monkeypatch, "disabled")
        assert resolve_mock_chat_model(SimpleNamespace(model_id="e2e-mock-agent-chat")) is None
        assert resolve_mock_chat_model(SimpleNamespace(model_id="e2e-mock-vision-chat")) is None
        assert resolve_mock_image_adapter(SimpleNamespace(model_id="e2e-mock-image-gen")) is None

    def test_mock_mode_should_not_replace_normal_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """mock 模式下普通 model ID 不被静默替换，由熔断阻止真实请求。"""

        _set_ai_test_mode(monkeypatch, "mock")
        assert resolve_mock_chat_model(SimpleNamespace(model_id="gpt-5-mini")) is None
        assert resolve_mock_image_adapter(SimpleNamespace(model_id="gpt-image-2")) is None

    def test_mock_mode_should_dispatch_by_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """agent/vision/image 三类 mock 按 model ID 独立分派。"""

        _set_ai_test_mode(monkeypatch, "mock")
        assert isinstance(resolve_mock_chat_model(SimpleNamespace(model_id="e2e-mock-agent-chat")), FunctionModel)
        assert isinstance(resolve_mock_chat_model(SimpleNamespace(model_id="e2e-mock-vision-chat")), FunctionModel)
        adapter = resolve_mock_image_adapter(SimpleNamespace(model_id="e2e-mock-image-gen"))
        assert isinstance(adapter, E2eMockImageGenerationAdapter)

    def test_resolver_should_inject_only_in_mock_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """模型解析入口只在 mock 模式下注入 FunctionModel，disabled 模式走真实校验。"""

        _set_ai_test_mode(monkeypatch, "mock")
        resolver = PydanticLlmModelResolver()
        model = resolver.resolve_model(_mock_chat_config(model_id="e2e-mock-agent-chat"))
        assert isinstance(model, FunctionModel)

        _set_ai_test_mode(monkeypatch, "disabled")
        with pytest.raises(AppException) as exc_info:
            resolver.resolve_model(_mock_chat_config(model_id="e2e-mock-agent-chat", status="archived"))
        assert exc_info.value.code == "AI_LLM_CONFIG_DISABLED"

    def test_resolver_should_reject_disabled_mock_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """mock 模型不能绕过供应商停用状态。"""

        _set_ai_test_mode(monkeypatch, "mock")
        with pytest.raises(AppException) as exc_info:
            PydanticLlmModelResolver().resolve_model(
                _mock_chat_config(model_id="e2e-mock-agent-chat", provider_status="archived")
            )
        assert exc_info.value.code == "AI_LLM_PROVIDER_CONFIG_DISABLED"

    def test_image_registry_should_inject_mock_adapter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """图片适配器注册入口只在 mock 模式下返回测试适配器。"""

        _set_ai_test_mode(monkeypatch, "mock")
        from app.services.image_generation.registry import get_image_generation_adapter

        config = SimpleNamespace(model_id="e2e-mock-image-gen")
        assert isinstance(get_image_generation_adapter(config), E2eMockImageGenerationAdapter)


class TestModelRequestFence:
    """覆盖真实模型请求熔断。"""

    def test_fence_should_block_real_model_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """熔断开启后，真实模型的请求检查立即失败。"""

        import pydantic_ai.models as pydantic_ai_models

        enforce_mock_model_request_fence()
        try:
            with pytest.raises(RuntimeError, match="ALLOW_MODEL_REQUESTS"):
                pydantic_ai_models.check_allow_model_requests()
        finally:
            pydantic_ai_models.ALLOW_MODEL_REQUESTS = True


class TestAgentScenarios:
    """覆盖内容助手场景状态机。"""

    def test_hello_scenario_should_return_final_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """普通对话场景 initial 直接到达终态文本。"""

        _set_ai_test_mode(monkeypatch, "mock")
        response = _respond(
            [ModelRequest(parts=[UserPromptPart(content=HELLO_SCENARIO_INPUT)])],
            _agent_info_with_tools(),
        )
        assert response.parts[0].content == "你好，我是内容助手的 E2E mock 响应，用于验证真实会话链路。"

    def test_visual_scenario_should_walk_full_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """视觉场景真实经历 analyze → generate → deferred 结果 → 终态。"""

        _set_ai_test_mode(monkeypatch, "mock")
        final_result = {"status": "completed", "assets": [{"id": 1, "name": "e2e-mock-visual-abcd-1"}]}
        response = _respond(_visual_history(final_result), _agent_info_with_tools())
        assert "配图已生成并保存到资源库" in response.parts[0].content
        assert "e2e-mock-visual-abcd-1" in response.parts[0].content

    def test_latest_user_turn_should_select_its_own_scenario(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """同一 Session 的新用户轮次不能被更早的普通对话输入劫持。"""

        _set_ai_test_mode(monkeypatch, "mock")
        visual_prompt = f"{VISUAL_SCENARIO_INPUT}\nattachment_id=42; name=ref.png"
        response = _respond(
            [
                ModelRequest(parts=[UserPromptPart(content=HELLO_SCENARIO_INPUT)]),
                ModelResponse(parts=[TextPart("上一轮已完成")]),
                ModelRequest(parts=[UserPromptPart(content=visual_prompt)]),
            ],
            _agent_info_with_tools(),
        )
        assert response.parts[0].tool_name == "analyze_visuals"

    def test_same_history_should_produce_same_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """相同历史重复请求必须得到一致响应，保证 deferred 重复恢复幂等。"""

        _set_ai_test_mode(monkeypatch, "mock")
        final_result = {"status": "completed", "assets": [{"id": 1, "name": "e2e-mock-visual-abcd-1"}]}
        history = _visual_history(final_result)
        first = _respond(history, _agent_info_with_tools())
        second = _respond(history, _agent_info_with_tools())
        assert first.parts[0].content == second.parts[0].content

    def test_unknown_input_should_raise_explicit_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未知初始输入立即报明确测试错误，不回退真实模型。"""

        _set_ai_test_mode(monkeypatch, "mock")
        with pytest.raises(MockScenarioError):
            _respond(
                [ModelRequest(parts=[UserPromptPart(content="完全无关的输入内容")])],
                _agent_info_with_tools(),
            )

    def test_unfinished_deferred_result_should_raise_explicit_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """generate_image 回灌非完成状态时属于未知终态，必须明确失败。"""

        _set_ai_test_mode(monkeypatch, "mock")
        history = _visual_history({"code": "AI_IMAGE_GENERATION_FAILED", "message": "失败"})
        with pytest.raises(MockScenarioError):
            _respond(history, _agent_info_with_tools())

    def test_compressor_call_should_not_enter_state_machine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """历史压缩调用（无工具）返回确定性文本，不进入内容助手状态机。"""

        _set_ai_test_mode(monkeypatch, "mock")
        info = AgentInfo(
            function_tools=[],
            allow_text_output=True,
            output_tools=[],
            model_settings=None,
            model_request_parameters=None,
            instructions=None,
        )
        response = _respond([ModelRequest(parts=[UserPromptPart(content="任意历史")])], info)
        assert "压缩" in response.parts[0].content

    def test_agent_model_should_expose_stream_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """平台 runner 走流式，FunctionModel 必须同时提供 stream_function。"""

        _set_ai_test_mode(monkeypatch, "mock")
        model = build_agent_function_model("e2e-mock-agent-chat")
        assert model.function is not None
        assert model.stream_function is not None


class TestVisionModel:
    """覆盖图片理解 FunctionModel。"""

    def test_vision_output_should_match_business_schema(self) -> None:
        """vision 输出必须符合 ImageUnderstandingOutput 业务 Schema。"""

        output = ImageUnderstandingOutput.model_validate(_build_output(3))
        assert [item.input_index for item in output.items] == [0, 1, 2]

    def test_vision_model_should_run_via_pydantic_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """vision FunctionModel 能在真实 Agent 调用中产出结构化结果。"""

        from pydantic_ai import Agent
        from pydantic_ai.messages import BinaryContent

        _set_ai_test_mode(monkeypatch, "mock")

        async def _run() -> ImageUnderstandingOutput:
            analyzer = Agent(
                build_vision_function_model("e2e-mock-vision-chat"),
                output_type=ImageUnderstandingOutput,
                system_prompt="测试",
            )
            result = await analyzer.run(
                ["input_count=1", BinaryContent(data=FIXED_MOCK_PNG, media_type="image/png")],
                infer_name=False,
            )
            return result.output

        import asyncio

        output = asyncio.run(_run())
        assert len(output.items) == 1


class TestImageAdapter:
    """覆盖图片生成测试适配器。"""

    def _build_request(self, *, count: int = 1, operation: str = "generate") -> ImageGenerationInput:
        """构造最小合法的图片生成输入。"""

        return ImageGenerationInput(
            operation=operation,
            prompt="E2E mock 提示词",
            aspect_ratio="auto",
            resolution_tier="auto",
            quality="auto",
            count=count,
            references=[],
        )

    def test_submit_should_return_fixed_png_without_http(self) -> None:
        """submit 同步返回固定合法 PNG，不产生外部请求。"""

        import asyncio

        adapter = E2eMockImageGenerationAdapter()
        model = get_image_model_spec("openai_image", "e2e-mock-image-gen")
        result = asyncio.run(
            adapter.submit(SimpleNamespace(), model, self._build_request(count=2))
        )
        assert result.status == "completed"
        assert len(result.images) == 2
        for image in result.images:
            assert image.content == FIXED_MOCK_PNG
            assert image.content.startswith(b"\x89PNG")

    def test_validate_should_reuse_model_capability_rules(self) -> None:
        """validate 复用真实模型能力校验，非法操作被拒绝。"""

        adapter = E2eMockImageGenerationAdapter()
        model = get_image_model_spec("openai_image", "e2e-mock-image-gen")
        with pytest.raises(AppException):
            adapter.validate(SimpleNamespace(), model, self._build_request(operation="unknown"))
