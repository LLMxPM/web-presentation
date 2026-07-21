"""文件功能：验证视觉工具目录、轻量附件上下文与通用 deferred requirement 契约。"""

from types import SimpleNamespace

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import BinaryContent, ToolCallPart

from app.ai.message_history import replace_agent_image_refs_with_placeholders
from app.ai.provider_catalog import get_llm_provider_entry
from app.ai.pydantic_runner import _requirement_from_deferred
from app.ai.session_facade_pydantic import AgentSessionFacade, _build_user_prompt
from app.ai.tool_specs import (
    build_agent_tools_from_group_specs,
    get_agent_tool_spec,
    list_agent_tool_specs,
    list_runtime_disclosure_groups,
)
from app.services.image_understanding_service import (
    ImageUnderstandingInput,
    ImageUnderstandingItem,
    ImageUnderstandingOutput,
    ImageUnderstandingService,
    _model_failure_detail,
    _resolve_image_analysis_model_settings,
)


def test_visual_tools_are_content_and_resource_agent_single_source_specs() -> None:
    """内容与资源助手应披露视觉工具，组件助手不应直接获得视觉能力。"""

    keys = {item.key for item in list_agent_tool_specs("agent-coordinator")}
    assert {"analyze_visuals", "generate_image"}.issubset(keys)
    resource_keys = {item.key for item in list_agent_tool_specs("resource-manager")}
    assert {"analyze_visuals", "generate_image"}.issubset(resource_keys)
    assert get_agent_tool_spec("component-manager", "analyze_visuals") is None
    assert get_agent_tool_spec("component-manager", "generate_image") is None


def test_visual_tools_use_independent_disclosure_groups_and_slot_filtering() -> None:
    """两个视觉工具必须独立披露，并可由各自槽位单独从本轮工具列表移除。"""

    assert list_runtime_disclosure_groups("agent-coordinator", "analyze_visuals") == ("image_analysis",)
    assert list_runtime_disclosure_groups("agent-coordinator", "generate_image") == ("image_generation",)

    analysis_only = build_agent_tools_from_group_specs(
        agent_id="agent-coordinator",
        session_factory=lambda: None,  # type: ignore[arg-type,return-value]
        unavailable_group_keys={"image_generation"},
    )
    generation_only = build_agent_tools_from_group_specs(
        agent_id="agent-coordinator",
        session_factory=lambda: None,  # type: ignore[arg-type,return-value]
        unavailable_group_keys={"image_analysis"},
    )
    assert "analyze_visuals" in {item.name for item in analysis_only}
    assert "generate_image" not in {item.name for item in analysis_only}
    assert "generate_image" in {item.name for item in generation_only}
    assert "analyze_visuals" not in {item.name for item in generation_only}


@pytest.mark.asyncio
async def test_visual_slot_availability_filters_groups_independently(monkeypatch) -> None:
    """内容助手应按两个槽位分别裁剪工具，且 external job 续跑保留原工具定义。"""

    class FakeLlmService:
        async def get_slot_binding_lookup(self):  # noqa: ANN201
            return {
                "image_understanding": SimpleNamespace(binding_ready=True),
                "image_generation": SimpleNamespace(binding_ready=False),
            }

    facade = object.__new__(AgentSessionFacade)
    monkeypatch.setattr(facade, "_llm_service", lambda: FakeLlmService())

    unavailable = await facade._resolve_unavailable_visual_tool_groups("agent-coordinator")
    resource_unavailable = await facade._resolve_unavailable_visual_tool_groups("resource-manager")
    component_unavailable = await facade._resolve_unavailable_visual_tool_groups("component-manager")
    retained = await facade._resolve_unavailable_visual_tool_groups(
        "agent-coordinator",
        retained_tool_names=frozenset({"generate_image"}),
    )

    assert unavailable == frozenset({"image_generation"})
    assert resource_unavailable == frozenset({"image_generation"})
    assert component_unavailable == frozenset()
    assert retained == frozenset()


@pytest.mark.asyncio
async def test_visual_tool_runtime_should_resolve_bound_image_model_once(monkeypatch) -> None:
    """视觉工具运行态应同时返回可见性、模型能力和同轮执行配置 ID。"""

    class FakeLlmService:
        async def get_slot_binding_lookup(self):  # noqa: ANN201
            return {
                "image_understanding": SimpleNamespace(binding_ready=True),
                "image_generation": SimpleNamespace(
                    binding_ready=True,
                    provider_key="dashscope_image",
                    model_id="wan2.7-image-pro",
                    llm_config_id=17,
                ),
            }

    facade = object.__new__(AgentSessionFacade)
    monkeypatch.setattr(facade, "_llm_service", lambda: FakeLlmService())

    unavailable, model, config_id = await facade._resolve_visual_tool_runtime("agent-coordinator")

    assert unavailable == frozenset()
    assert model is not None
    assert model.model_id == "wan2.7-image-pro"
    assert config_id == 17


def test_image_provider_catalog_is_separated_from_chat_provider() -> None:
    """OpenAI Chat 与图片供应商应使用独立 key 和单一模型类型。"""

    chat_provider = get_llm_provider_entry("openai")
    image_provider = get_llm_provider_entry("openai_image")
    assert chat_provider.provider_type == "chat"
    assert chat_provider.supported_model_types == ("chat",)
    assert image_provider.provider_type == "image_generation"
    assert image_provider.supported_model_types == ("image_generation",)
    assert image_provider.default_image_generation_model_id == "gpt-image-2"
    assert image_provider.provider_adapter.endswith(".OpenAiImageGenerationAdapter")
    assert image_provider.image_generation_models[0]["model_id"] == "gpt-image-2"
    assert image_provider.image_generation_models[0]["supports_mask"] is True


def test_content_prompt_only_contains_lightweight_attachment_metadata() -> None:
    """内容模型输入只包含附件元数据，不得出现对象 key、bytes 或 URL。"""

    attachment = SimpleNamespace(
        id=7,
        original_name="reference.png",
        content_type="image/png",
        file_size=1234,
        width=1024,
        height=768,
        storage_key="secret/local/reference.png",
        model_url="https://example.test/signed",
    )
    prompt = _build_user_prompt("比较版式", [attachment])

    assert "attachment_id=7" in prompt
    assert "reference.png" in prompt
    assert "secret/local" not in prompt
    assert "https://" not in prompt


def test_image_generation_deferred_call_builds_external_job_requirement() -> None:
    """图片任务应进入无需用户确认的通用 external_job requirement。"""

    requests = DeferredToolRequests(
        calls=[ToolCallPart(tool_name="generate_image", args={"prompt": "hero"}, tool_call_id="tool-image-1")],
        metadata={"tool-image-1": {"kind": "image_generation", "job_id": "ai-image-job-1"}},
    )
    requirement = _requirement_from_deferred(requests, run_id="run-1", session_id="session-1")

    assert requirement.kind == "external_job"
    assert requirement.tool_execution["job_ids"] == ["ai-image-job-1"]
    assert requirement.tool_execution["requires_user_input"] is False


def test_historical_image_ref_becomes_text_placeholder() -> None:
    """历史图片引用必须转换为文本占位而不是重新水合像素。"""

    value = [{"kind": "agent-image-ref", "attachment_id": 9, "original_name": "old.png"}]
    assert replace_agent_image_refs_with_placeholders(value) == ["[图片引用：old.png]"]


@pytest.mark.asyncio
async def test_image_understanding_service_uses_one_shot_request_and_injects_source(monkeypatch) -> None:
    """图片理解服务应隔离历史，并由平台注入可信来源和尺寸。"""
    model_config = SimpleNamespace(
        id=3,
        name="视觉模型",
        model_id="gpt-4.1-mini",
        provider_config=SimpleNamespace(provider_key="openai"),
    )
    captured: dict[str, object] = {}

    class FakeAnalyzer:
        def __init__(self, model, **kwargs):  # noqa: ANN001, ANN003
            captured["model"] = model
            captured["agent_kwargs"] = kwargs

        async def run(self, parts, **kwargs):  # noqa: ANN001, ANN003
            captured["parts"] = parts
            captured["run_kwargs"] = kwargs
            return SimpleNamespace(
                output=ImageUnderstandingOutput(
                    summary="一张横向图片",
                    items=[ImageUnderstandingItem(input_index=0, description="蓝色横幅")],
                )
            )

    async def fake_bound_config(self, slot):  # noqa: ANN001
        assert slot == "image_understanding"
        return model_config

    monkeypatch.setattr("app.services.image_understanding_service.AiLlmService.get_bound_config_or_raise", fake_bound_config)
    monkeypatch.setattr("app.services.image_understanding_service.PydanticLlmModelResolver.resolve_model", lambda self, config: "vision-model")
    monkeypatch.setattr("app.services.image_understanding_service.PydanticLlmModelResolver.resolve_model_settings", lambda self, config: {})
    monkeypatch.setattr("app.services.image_understanding_service.Agent", FakeAnalyzer)

    result = await ImageUnderstandingService(object(), user_id=1).analyze(  # type: ignore[arg-type]
        inputs=[ImageUnderstandingInput(
            source={"source_type": "attachment", "attachment_id": 7},
            content=b"local-image-bytes",
            content_type="image/png",
            width=640,
            height=360,
        )],
        instruction="描述图片",
        analysis_type="general",
        detail="auto",
    )

    assert captured["model"] == "vision-model"
    assert "message_history" not in captured["run_kwargs"]
    assert any(isinstance(part, BinaryContent) and part.data == b"local-image-bytes" for part in captured["parts"])
    assert result["items"][0]["source"] == {"source_type": "attachment", "attachment_id": 7}
    assert result["items"][0]["dimensions"] == {"width": 640, "height": 360}
    assert result["items"][0]["aspect_ratio"] == "16:9"


def test_dashscope_image_understanding_disables_thinking_for_structured_output() -> None:
    """DashScope 视觉结构化输出应关闭思考模式，避免与强制结果工具冲突。"""

    model_config = SimpleNamespace(provider_config=SimpleNamespace(provider_key="dashscope"))

    class FakeResolver:
        def resolve_model_settings(self, config):  # noqa: ANN001
            assert config is model_config
            return {
                "max_tokens": 64000,
                "extra_body": {"enable_thinking": True, "thinking_budget": 10000},
            }

    settings = _resolve_image_analysis_model_settings(model_config, FakeResolver())  # type: ignore[arg-type]

    assert settings == {
        "max_tokens": 64000,
        "extra_body": {"enable_thinking": False},
    }


def test_image_understanding_failure_detail_classifies_dashscope_bad_request() -> None:
    """DashScope 400 应返回模型能力提示，且不暴露供应商响应正文。"""

    exc = ModelHTTPError(
        status_code=400,
        model_name="qwen3.7-plus",
        body={"message": "sensitive upstream detail"},
    )

    detail = _model_failure_detail(exc, provider_key="dashscope")

    assert "图片输入与结构化输出" in detail
    assert "sensitive upstream detail" not in detail
