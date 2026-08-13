"""文件功能：解析聊天模型能力档案，并把平台四档推理策略映射为供应商原生参数。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fnmatch import fnmatch
from typing import Any

from app.models.enums import AiReasoningLevel, AiReasoningMode

CAPABILITY_PROFILE_VERSION = 2
PLATFORM_REASONING_LEVELS = tuple(item.value for item in AiReasoningLevel)
UNKNOWN_MODEL_CONTEXT_WINDOW_DEFAULT = 1_000_000
UNKNOWN_MODEL_CONTEXT_WINDOW_MAX = 1_000_000


@dataclass(frozen=True, slots=True)
class ModelCapabilityProfile:
    """描述模型能力及平台四档到供应商原生值的稳定映射。"""

    key: str
    provider_key: str
    model_pattern: str
    context_window_tokens: int
    model_max_output_tokens: int
    supports_image_input: bool
    supports_reasoning: bool
    supports_explicit_disable: bool
    default_level: str | None
    native_levels: tuple[str, ...]
    level_mapping: dict[str, str | int | None]
    source: str = "built_in"
    verified: bool = True
    supports_reasoning_budget: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedModelCapability:
    """保存模型最终能力、来源和可直接写入配置快照的映射。"""

    profile: ModelCapabilityProfile
    warnings: tuple[str, ...] = ()

    def effective_reasoning(self, mode: str, level: str | None) -> dict[str, Any]:
        """解析用户策略为供应商原生值，并返回可解释的生效信息。"""

        if mode == AiReasoningMode.AUTO.value:
            return {"mode": mode, "requested_level": None, "native_value": None, "degraded": False, "message": "跟随模型默认。"}
        if mode == AiReasoningMode.DISABLED.value:
            return {
                "mode": mode,
                "requested_level": None,
                "native_value": "disabled" if self.profile.supports_explicit_disable else None,
                "degraded": False,
                "message": "显式关闭推理。" if self.profile.supports_explicit_disable else "当前能力档案不支持显式关闭。",
            }
        requested = level or self.profile.default_level or AiReasoningLevel.MEDIUM.value
        native = self.profile.level_mapping.get(requested)
        if not self.profile.supports_reasoning:
            native = None
        degraded = native not in {requested, requested.upper()}
        message = "强度不参与供应商请求，仅启用推理。" if native is None and self.profile.supports_reasoning else f"最终生效：{native or '不支持'}。"
        return {"mode": mode, "requested_level": requested, "native_value": native, "degraded": degraded, "message": message}

    def as_dict(self) -> dict[str, Any]:
        """转换为数据库和 API 可复用的 JSON 结构。"""

        item = self.profile
        return {
            "profile_key": item.key,
            "profile_version": CAPABILITY_PROFILE_VERSION,
            "source": item.source,
            "verified": item.verified,
            "context_window_tokens": item.context_window_tokens,
            "model_max_output_tokens": item.model_max_output_tokens,
            "supports_image_input": item.supports_image_input,
            "supports_reasoning": item.supports_reasoning,
            "supports_explicit_disable": item.supports_explicit_disable,
            "supports_reasoning_budget": item.supports_reasoning_budget,
            "default_level": item.default_level,
            "native_levels": list(item.native_levels),
            "level_mapping": dict(item.level_mapping),
            "warnings": list(self.warnings),
        }


def _profile(
    key: str,
    provider_key: str,
    model_pattern: str,
    *,
    context: int,
    max_output: int,
    image: bool = False,
    reasoning: bool = True,
    disable: bool = False,
    default: str | None = "medium",
    native: tuple[str, ...] = ("low", "medium", "high"),
    mapping: dict[str, str | int | None] | None = None,
    budget: bool = False,
    verified: bool = True,
) -> ModelCapabilityProfile:
    """构造紧凑的内置能力档案。"""

    return ModelCapabilityProfile(
        key=key,
        provider_key=provider_key,
        model_pattern=model_pattern,
        context_window_tokens=context,
        model_max_output_tokens=max_output,
        supports_image_input=image,
        supports_reasoning=reasoning,
        supports_explicit_disable=disable,
        default_level=default if reasoning else None,
        native_levels=native if reasoning else (),
        level_mapping=mapping or {"low": "low", "medium": "medium", "high": "high", "max": native[-1] if native else None},
        supports_reasoning_budget=budget,
        verified=verified,
    )


MODEL_CAPABILITY_PROFILES = (
    _profile("openai-gpt-5.6", "openai", "gpt-5.6", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-gpt-5.6-sol", "openai", "gpt-5.6-sol", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-gpt-5.6-terra", "openai", "gpt-5.6-terra", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-gpt-5.6-luna", "openai", "gpt-5.6-luna", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-gpt-5.6-family", "openai", "gpt-5.6*", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-gpt-5.2-5.5", "openai", "gpt-5.[2-5]*", context=400_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "xhigh"}),
    _profile("openai-gpt-4.1", "openai", "gpt-4.1*", context=1_000_000, max_output=32_768, image=True, reasoning=False),
    _profile("openai-like-gpt-5.6", "openai_like", "gpt-5.6", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-like-gpt-5.6-sol", "openai_like", "gpt-5.6-sol", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-like-gpt-5.6-terra", "openai_like", "gpt-5.6-terra", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-like-gpt-5.6-luna", "openai_like", "gpt-5.6-luna", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-like-gpt-5.6-family", "openai_like", "gpt-5.6*", context=1_050_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-like-gpt-5.2-5.5", "openai_like", "gpt-5.[2-5]*", context=400_000, max_output=128_000, image=True, disable=True, native=("low", "medium", "high", "xhigh"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "xhigh"}),
    _profile("openai-like-gpt-4.1", "openai_like", "gpt-4.1*", context=1_000_000, max_output=32_768, image=True, reasoning=False),
    _profile("dashscope-qwen3.8-max", "dashscope", "qwen3.8-max*", context=1_000_000, max_output=64_000, disable=True, native=("2000", "5000", "10000"), mapping={"low": 2_000, "medium": 5_000, "high": 10_000, "max": 10_000}, budget=True, verified=False),
    _profile("openai-like-kimi-k3", "openai_like", "kimi-k3*", context=1_000_000, max_output=64_000, image=True, disable=False, native=("high",), mapping={"low": "high", "medium": "high", "high": "high", "max": "high"}, verified=False),
    _profile("openai-like-glm-5.2", "openai_like", "glm-5.2*", context=1_000_000, max_output=128_000, disable=False, native=("low", "medium", "high", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openrouter-qwen3.8-max", "openrouter", "qwen/qwen3.8-max*", context=1_000_000, max_output=64_000, disable=False, native=("low", "medium", "high"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "high"}, verified=False),
    _profile("openrouter-kimi-k3", "openrouter", "moonshotai/kimi-k3*", context=1_000_000, max_output=64_000, image=True, disable=False, native=("high",), mapping={"low": "high", "medium": "high", "high": "high", "max": "high"}, verified=False),
    _profile("openrouter-glm-5.2", "openrouter", "z-ai/glm-5.2*", context=1_000_000, max_output=128_000, disable=False, native=("low", "medium", "high", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
    _profile("openai-like-qwen3.8-max", "openai_like", "qwen3.8-max*", context=1_000_000, max_output=64_000, disable=True, native=("2000", "5000", "10000"), mapping={"low": 2_000, "medium": 5_000, "high": 10_000, "max": 10_000}, budget=True, verified=False),
    _profile("openai-like-openrouter-qwen3.8-max", "openai_like", "qwen/qwen3.8-max*", context=1_000_000, max_output=64_000, disable=False, native=("low", "medium", "high"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "high"}, verified=False),
    _profile("openai-like-openrouter-kimi-k3", "openai_like", "moonshotai/kimi-k3*", context=1_000_000, max_output=64_000, image=True, disable=False, native=("high",), mapping={"low": "high", "medium": "high", "high": "high", "max": "high"}, verified=False),
    _profile("openai-like-openrouter-glm-5.2", "openai_like", "z-ai/glm-5.2*", context=1_000_000, max_output=128_000, disable=False, native=("low", "medium", "high", "max"), mapping={"low": "low", "medium": "medium", "high": "high", "max": "max"}),
)


def _provider_default(provider_key: str, *, context_window_tokens: int | None, model_max_output_tokens: int | None, supports_image_input: bool) -> ModelCapabilityProfile:
    """创建未知模型的供应商默认档案，保持兼容但明确标记未验证。"""

    context = min(int(context_window_tokens or UNKNOWN_MODEL_CONTEXT_WINDOW_DEFAULT), UNKNOWN_MODEL_CONTEXT_WINDOW_MAX)
    output = int(model_max_output_tokens or 65_536)
    common = {"low": "low", "medium": "medium", "high": "high", "max": "high"}
    presets: dict[str, dict[str, Any]] = {
        "google": {"disable": False, "native": ("LOW", "HIGH"), "mapping": {"low": "LOW", "medium": "HIGH", "high": "HIGH", "max": "HIGH"}, "default": "high"},
        "dashscope": {"disable": True, "native": ("2000", "5000", "10000"), "mapping": {"low": 2_000, "medium": 5_000, "high": 10_000, "max": 10_000}, "budget": True},
        "deepseek": {"disable": True, "native": ("high", "max"), "mapping": {"low": "high", "medium": "high", "high": "high", "max": "max"}, "default": "high"},
        "mimo": {"disable": True, "native": (), "mapping": {level: None for level in PLATFORM_REASONING_LEVELS}, "default": "medium"},
        "ollama": {"disable": True, "native": ("low", "medium", "high"), "mapping": common},
    }
    values = presets.get(provider_key, {"disable": False, "native": ("low", "medium", "high"), "mapping": common})
    return ModelCapabilityProfile(
        key=f"{provider_key}-provider-default",
        provider_key=provider_key,
        model_pattern="*",
        context_window_tokens=context,
        model_max_output_tokens=output,
        supports_image_input=supports_image_input,
        supports_reasoning=True,
        supports_explicit_disable=bool(values.get("disable", False)),
        default_level=str(values.get("default", "medium")),
        native_levels=tuple(values["native"]),
        level_mapping=dict(values["mapping"]),
        source="provider_default",
        verified=False,
        supports_reasoning_budget=bool(values.get("budget", False)),
    )


def resolve_model_capability(
    provider_key: str,
    model_id: str,
    *,
    default_context_window_tokens: int | None = None,
    default_model_max_output_tokens: int | None = None,
    default_supports_image_input: bool = False,
    override: dict[str, Any] | None = None,
) -> ResolvedModelCapability:
    """按手工覆盖、模型档案、供应商默认的优先级解析最终能力。"""

    normalized_provider = provider_key.strip().lower()
    normalized_model = model_id.strip().lower()
    provider_profiles = tuple(item for item in MODEL_CAPABILITY_PROFILES if item.provider_key == normalized_provider)
    matched = next((item for item in provider_profiles if normalized_model == item.model_pattern.lower()), None)
    matched = matched or next((item for item in provider_profiles if fnmatch(normalized_model, item.model_pattern.lower())), None)
    if matched is None and normalized_provider == "openrouter" and normalized_model.startswith("openai/"):
        upstream_model = normalized_model.split("/", 1)[1]
        upstream = next((item for item in MODEL_CAPABILITY_PROFILES if item.provider_key == "openai" and fnmatch(upstream_model, item.model_pattern.lower())), None)
        if upstream is not None:
            matched = replace(upstream, key=f"openrouter-{upstream.key}", provider_key="openrouter")
    profile = matched or _provider_default(
        normalized_provider,
        context_window_tokens=default_context_window_tokens,
        model_max_output_tokens=default_model_max_output_tokens,
        supports_image_input=default_supports_image_input,
    )
    # 能力来源和验证状态由结构化字段表达，提示只保留给用户可执行的确认动作。
    warnings: tuple[str, ...] = ()
    if override:
        level_mapping = dict(profile.level_mapping)
        override_mapping = override.get("level_mapping")
        if isinstance(override_mapping, dict):
            level_mapping.update({level: override_mapping[level] for level in PLATFORM_REASONING_LEVELS if level in override_mapping})
        native_levels_value = override.get("native_levels", profile.native_levels)
        native_levels = tuple(str(item) for item in native_levels_value) if isinstance(native_levels_value, (list, tuple)) else profile.native_levels
        default_level_value = override.get("default_level", profile.default_level)
        default_level = str(default_level_value) if default_level_value in PLATFORM_REASONING_LEVELS else profile.default_level
        supports_reasoning = bool(override.get("supports_reasoning", profile.supports_reasoning))
        profile = replace(
            profile,
            key=f"{profile.key}-manual",
            context_window_tokens=int(override.get("context_window_tokens", profile.context_window_tokens)),
            model_max_output_tokens=int(override.get("model_max_output_tokens", profile.model_max_output_tokens)),
            supports_image_input=bool(override.get("supports_image_input", profile.supports_image_input)),
            supports_reasoning=supports_reasoning,
            supports_explicit_disable=bool(override.get("supports_explicit_disable", profile.supports_explicit_disable)),
            supports_reasoning_budget=bool(override.get("supports_reasoning_budget", profile.supports_reasoning_budget)),
            default_level=default_level if supports_reasoning else None,
            native_levels=native_levels if supports_reasoning else (),
            level_mapping=level_mapping if supports_reasoning else {level: None for level in PLATFORM_REASONING_LEVELS},
            source="manual_override",
            verified=False,
        )
        warnings = ()
    return ResolvedModelCapability(profile=profile, warnings=warnings)


def capability_from_snapshot(value: dict[str, Any]) -> ResolvedModelCapability | None:
    """从配置或 Run 快照恢复能力，避免注册表更新改变既有运行。"""

    if not isinstance(value, dict) or not value.get("profile_key"):
        return None
    try:
        profile = ModelCapabilityProfile(
            key=str(value["profile_key"]), provider_key=str(value.get("provider_key", "snapshot")), model_pattern="*",
            context_window_tokens=int(value["context_window_tokens"]), model_max_output_tokens=int(value["model_max_output_tokens"]),
            supports_image_input=bool(value.get("supports_image_input")), supports_reasoning=bool(value.get("supports_reasoning")),
            supports_explicit_disable=bool(value.get("supports_explicit_disable")), default_level=value.get("default_level"),
            native_levels=tuple(str(item) for item in value.get("native_levels", [])), level_mapping=dict(value.get("level_mapping", {})),
            source=str(value.get("source", "snapshot")), verified=bool(value.get("verified")), supports_reasoning_budget=bool(value.get("supports_reasoning_budget")),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return ResolvedModelCapability(profile=profile, warnings=tuple(str(item) for item in value.get("warnings", [])))
