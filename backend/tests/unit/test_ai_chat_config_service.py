"""文件功能：验证聊天配置的推理选项与固定协议边界。"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import AppException
from app.schemas.model_config import ReasoningPolicy
from app.services.ai_chat_config_service import AiChatConfigService
from app.services.ai_llm_service import AiLlmService


def _capability(**overrides: object) -> dict[str, object]:
    """构造满足预算约束的目录能力。"""

    value: dict[str, object] = {
        "context_tokens": 200_000,
        "input_tokens": 190_000,
        "output_tokens": 10_000,
        "supports_tool_call": True,
        "supports_image_input": True,
        "supports_reasoning": True,
        "reasoning_options": {"types": ["toggle", "effort"], "effort": ["none", "low", "high"]},
    }
    value.update(overrides)
    return value


def test_effort_must_be_published_by_catalog() -> None:
    """用户强度必须同时属于目录枚举和平台固定转换器。"""

    service = AiChatConfigService.__new__(AiChatConfigService)
    service._validate_policy("agent_coordinator", "openai_chat", _capability(), ReasoningPolicy(mode="effort", value="high"))
    with pytest.raises(AppException) as error:
        service._validate_policy("agent_coordinator", "openai_chat", _capability(), ReasoningPolicy(mode="effort", value="xhigh"))
    assert error.value.code == "AI_CHAT_REASONING_EFFORT_UNSUPPORTED"


def test_generic_compatible_provider_uses_models_dev_effort_only() -> None:
    """通用 OpenAI-compatible 仅开放 Models.dev 明确声明的标准 effort。"""

    service = AiChatConfigService.__new__(AiChatConfigService)
    service._validate_policy(
        "agent_coordinator",
        "openai_compatible_chat",
        _capability(reasoning_options={"types": ["effort"], "effort": ["high", "max"]}),
        ReasoningPolicy(mode="effort", value="max"),
    )
    with pytest.raises(AppException) as error:
        service._validate_policy(
            "agent_coordinator",
            "openai_compatible_chat",
            _capability(reasoning_options={"types": ["toggle"]}),
            ReasoningPolicy(mode="disabled"),
        )
    assert error.value.code == "AI_CHAT_REASONING_DISABLE_UNSUPPORTED"


def test_reasoning_controls_require_model_and_protocol_intersection() -> None:
    """关闭、强度和预算必须同时得到模型元数据与固定协议转换器支持。"""

    service = AiChatConfigService.__new__(AiChatConfigService)
    effort_only = _capability(reasoning_options={"types": ["effort"], "effort": ["low", "high"]})
    with pytest.raises(AppException) as disabled_error:
        service._validate_policy("agent_coordinator", "google_chat", effort_only, ReasoningPolicy(mode="disabled"))
    assert disabled_error.value.code == "AI_CHAT_REASONING_DISABLE_UNSUPPORTED"

    budget = _capability(reasoning_options={"types": ["budget_tokens"], "budget_tokens": {"min": 1024}})
    service._validate_policy("agent_coordinator", "alibaba_openai_compatible", budget, ReasoningPolicy(mode="budget_tokens", value=2048))
    with pytest.raises(AppException) as budget_error:
        service._validate_policy("agent_coordinator", "openai_chat", budget, ReasoningPolicy(mode="budget_tokens", value=2048))
    assert budget_error.value.code == "AI_CHAT_REASONING_BUDGET_UNSUPPORTED"

    with pytest.raises(AppException) as range_error:
        service._validate_policy("agent_coordinator", "alibaba_openai_compatible", budget, ReasoningPolicy(mode="budget_tokens", value=512))
    assert range_error.value.code == "AI_CHAT_REASONING_BUDGET_INVALID"


def test_run_policy_uses_model_input_and_platform_output_cap() -> None:
    """Run 输入直接采用模型参数，输出统一封顶 32K，推理策略只附着到本轮对象。"""

    provider = SimpleNamespace(provider_key="openai", protocol_key="openai_chat")
    capability = _capability(
        context_tokens=300_000,
        input_tokens=240_000,
        output_tokens=60_000,
        reasoning_options={"types": ["effort"], "effort": ["low", "medium", "high"]},
        source="models.dev",
        verified=True,
    )
    snapshot = AiChatConfigService._legacy_capability_snapshot(provider, "reasoning-model", capability)
    assert snapshot["protocol_key"] == "openai_chat"
    config = SimpleNamespace(
        provider_config=provider,
        model_capability_json=snapshot,
        context_window_tokens=240_000,
        reasoning_mode="auto",
        reasoning_level=None,
    )
    service = AiLlmService.__new__(AiLlmService)
    service.session = None
    service.user_id = 1
    service.user_role = "workspace_user"

    service.apply_run_reasoning_policy(
        config,
        slot="agent_coordinator",
        reasoning=ReasoningPolicy(mode="effort", value="medium"),
    )
    budget = service._derive_config_run_budget(config)

    assert config.reasoning_mode == "enabled"
    assert config.reasoning_level == "medium"
    assert config._usage_policy_json == {"reasoning": {"mode": "effort", "value": "medium"}}
    assert budget.context_input_budget_tokens == 240_000
    assert budget.max_output_tokens == 32_768
