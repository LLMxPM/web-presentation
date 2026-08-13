"""文件功能：验证模型能力档案、四档映射与未知模型回退语义。"""

from app.ai.model_capabilities import capability_from_snapshot, resolve_model_capability
from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.models.enums import AiThinkingMode


def test_openai_56_should_keep_platform_max() -> None:
    """原生支持 max 的模型不应降级。"""

    capability = resolve_model_capability("openai", "gpt-5.6")

    assert capability.profile.verified is True
    assert capability.effective_reasoning("enabled", "max")["native_value"] == "max"
    assert capability.profile.supports_explicit_disable is True


def test_openai_55_should_degrade_max_to_xhigh() -> None:
    """不支持 max 但支持 xhigh 的模型应选择原生最高档。"""

    capability = resolve_model_capability("openai", "gpt-5.5")

    effective = capability.effective_reasoning("enabled", "max")
    assert effective["native_value"] == "xhigh"
    assert effective["degraded"] is True


def test_unknown_model_should_use_unverified_provider_default() -> None:
    """未知模型允许创建，但必须明确标记能力未经验证。"""

    capability = resolve_model_capability("openai_like", "custom-model")

    assert capability.profile.source == "provider_default"
    assert capability.profile.verified is False
    assert capability.profile.model_max_output_tokens == 65_536
    assert capability.profile.context_window_tokens == 1_000_000

    large_provider_default = resolve_model_capability(
        "deepseek",
        "future-unknown-model",
        default_context_window_tokens=1_000_000,
    )
    assert large_provider_default.profile.context_window_tokens == 1_000_000


def test_manual_override_should_cover_reasoning_capabilities_and_four_level_mapping() -> None:
    """手工覆盖应能声明显式关闭能力，并仅替换提供的四档映射。"""

    capability = resolve_model_capability(
        "openai_like",
        "vendor-reasoner",
        override={
            "supports_explicit_disable": True,
            "native_levels": ["low", "high", "xhigh"],
            "level_mapping": {"max": "xhigh"},
        },
    )

    assert capability.profile.source == "manual_override"
    assert capability.profile.supports_explicit_disable is True
    assert capability.profile.native_levels == ("low", "high", "xhigh")
    assert capability.profile.level_mapping == {"low": "low", "medium": "medium", "high": "high", "max": "xhigh"}
    assert capability.warnings == ()


def test_capability_snapshot_should_preserve_mapping() -> None:
    """Run 恢复应使用固化映射而不是重新读取注册表。"""

    original = resolve_model_capability("deepseek", "custom-model", default_context_window_tokens=1_000_000)
    snapshot = {**original.as_dict(), "provider_key": "deepseek"}

    restored = capability_from_snapshot(snapshot)

    assert restored is not None
    assert restored.effective_reasoning("enabled", "max")["native_value"] == "max"


def test_latest_model_profiles_should_expose_declared_capabilities() -> None:
    """最新模型应命中明确档案，未知输出能力使用带警告的保守值。"""

    sol = resolve_model_capability("openai", "gpt-5.6-sol")
    luna = resolve_model_capability("openai", "gpt-5.6-luna")
    qwen = resolve_model_capability("dashscope", "qwen3.8-max")
    kimi = resolve_model_capability("openai_like", "kimi-k3")
    glm = resolve_model_capability("openai_like", "glm-5.2")
    openai_like_gpt = resolve_model_capability("openai_like", "gpt-5.6")
    openai_like_qwen = resolve_model_capability("openai_like", "qwen3.8-max")

    assert (sol.profile.context_window_tokens, sol.profile.model_max_output_tokens) == (1_050_000, 128_000)
    assert (luna.profile.context_window_tokens, luna.profile.model_max_output_tokens) == (1_050_000, 128_000)
    assert qwen.profile.context_window_tokens == 1_000_000
    assert qwen.profile.verified is False and qwen.warnings == ()
    assert kimi.profile.supports_image_input is True
    assert kimi.profile.verified is False and kimi.warnings == ()
    assert (glm.profile.context_window_tokens, glm.profile.model_max_output_tokens) == (1_000_000, 128_000)
    assert glm.effective_reasoning("enabled", "max")["native_value"] == "max"
    assert (openai_like_gpt.profile.context_window_tokens, openai_like_gpt.profile.model_max_output_tokens) == (1_050_000, 128_000)
    assert openai_like_gpt.profile.verified is True
    assert (openai_like_qwen.profile.context_window_tokens, openai_like_qwen.profile.model_max_output_tokens) == (1_000_000, 64_000)
    assert openai_like_qwen.profile.verified is False


def test_generic_openai_compatible_should_translate_catalog_effort() -> None:
    """通用兼容协议应把 Models.dev effort 转成标准 reasoning_effort 参数。"""

    assert PydanticLlmModelResolver._resolve_thinking_mode(
        "opencode-go",
        "openai_compatible_chat",
    ) == AiThinkingMode.OPENAI_REASONING.value
