"""文件功能：把平台大模型配置解析为 Pydantic AI 可执行模型对象。"""

from __future__ import annotations

from typing import Any

from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.ai.llm_http_trace import build_llm_http_trace_client
from app.ai.model_capabilities import capability_from_snapshot, resolve_model_capability
from app.ai.model_budget import CONTEXT_WINDOW_TOKEN_DEFAULT, derive_model_run_budget
from app.ai.provider_catalog import MIMO_MAX_COMPLETION_TOKENS, get_llm_provider_entry
from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_llm import AiLlmConfig
from app.models.enums import AiReasoningMode, AiThinkingMode, RecordStatus

DASHSCOPE_THINKING_BUDGETS = {
    "low": 2_000,
    "medium": 5_000,
    "high": 10_000,
}


class PydanticLlmModelResolver:
    """把数据库大模型配置翻译为 Pydantic AI 模型对象和运行参数。"""

    def __init__(self) -> None:
        """初始化密钥解密器。"""

        self._cipher = LlmSecretCipher()

    def resolve_model(self, config: AiLlmConfig) -> Any:
        """根据用户模型配置生成 Pydantic AI model。"""

        if config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_LLM_CONFIG_DISABLED", detail="当前大模型配置不可用。")
        provider_config = self._get_provider_config(config)
        if provider_config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_LLM_PROVIDER_CONFIG_DISABLED", detail="当前大模型供应商配置不可用。")
        provider_key = str(provider_config.provider_key or "").strip()
        protocol_key = str(getattr(config, "protocol_key", "") or getattr(provider_config, "protocol_key", "") or "").strip()

        # E2E mock 仍遵守模型与供应商启用状态；仅跳过真实协议对象的创建和凭证解析。
        from app.ai.testing.dispatch import resolve_mock_chat_model

        mock_model = resolve_mock_chat_model(config)
        if mock_model is not None:
            return mock_model

        model_id = str(config.model_id or "").strip()
        api_key = self._cipher.decrypt(provider_config.api_key_ciphertext)
        base_url = str(provider_config.base_url or "").strip() or None

        if not model_id:
            raise AppException(status_code=400, code="AI_LLM_MODEL_ID_REQUIRED", detail="当前大模型配置缺少模型 ID。")

        http_client = build_llm_http_trace_client(config)

        if protocol_key == "google_chat" or provider_key == "google":
            return GoogleModel(model_id, provider=GoogleProvider(api_key=api_key or None, base_url=base_url, http_client=http_client))
        if protocol_key == "openrouter_chat" or provider_key == "openrouter":
            return OpenRouterModel(model_id, provider=OpenRouterProvider(api_key=api_key or None, http_client=http_client))
        if protocol_key == "ollama_openai_compatible" or provider_key == "ollama":
            return OpenAIChatModel(
                model_id,
                provider=OllamaProvider(base_url=base_url or "http://localhost:11434/v1", http_client=http_client),
            )
        if protocol_key == "alibaba_openai_compatible" or provider_key == "dashscope":
            return OpenAIChatModel(
                model_id,
                provider=AlibabaProvider(api_key=api_key or None, base_url=base_url, http_client=http_client),
            )
        if protocol_key == "deepseek_openai_compatible" or provider_key == "deepseek":
            return OpenAIChatModel(model_id, provider=DeepSeekProvider(api_key=api_key or None, http_client=http_client))
        if protocol_key in {"openai_chat", "openai_compatible_chat", "xiaomi_openai_compatible"} or provider_key in {"openai", "openai_like", "nvidia", "mimo"}:
            if protocol_key in {"openai_compatible_chat", "xiaomi_openai_compatible"} and not base_url:
                raise AppException(status_code=400, code="AI_LLM_BASE_URL_REQUIRED", detail="OpenAI-compatible 聊天供应商必须配置 Base URL。")
            return OpenAIChatModel(
                model_id,
                provider=OpenAIProvider(api_key=api_key or None, base_url=base_url, http_client=http_client),
            )
        raise AppException(status_code=400, code="AI_LLM_PROVIDER_UNSUPPORTED", detail="当前供应商暂不支持 Pydantic AI。")

    def resolve_model_settings(self, config: AiLlmConfig) -> dict[str, Any]:
        """把平台运行参数翻译为 Pydantic AI model_settings。"""

        settings: dict[str, Any] = {}
        advanced_config = config.advanced_config_json or {}
        if isinstance(advanced_config, dict):
            settings.update(advanced_config)
        context_window_tokens = int(config.context_window_tokens or CONTEXT_WINDOW_TOKEN_DEFAULT)
        capability = self._resolve_capability(config)
        provider_key = self._resolve_provider_key(config)
        output_limit = capability.profile.model_max_output_tokens
        if provider_key == "mimo":
            output_limit = min(output_limit, MIMO_MAX_COMPLETION_TOKENS)
        legacy_output = getattr(config, "request_max_output_tokens", None) or getattr(config, "max_output_tokens", None)
        policy_output = getattr(config, "request_output_tokens", None)
        settings["max_tokens"] = (
            int(policy_output)
            if getattr(config, "budget_policy_version", None) and policy_output
            else int(legacy_output)
            if not getattr(config, "budget_policy_version", None) and legacy_output
            else derive_model_run_budget(context_window_tokens, provider_output_limit=output_limit).max_output_tokens
        )
        self._apply_provider_limits(config, settings)
        self._apply_thinking_settings(config, settings)
        return settings

    def _apply_provider_limits(self, config: AiLlmConfig, settings: dict[str, Any]) -> None:
        """按供应商硬限制修正运行参数，避免已保存旧配置持续触发模型 400。"""

        if self._resolve_provider_key(config) != "mimo":
            return
        max_tokens = settings.get("max_tokens")
        if not isinstance(max_tokens, int) or max_tokens <= MIMO_MAX_COMPLETION_TOKENS:
            return
        settings["max_tokens"] = MIMO_MAX_COMPLETION_TOKENS

    def _apply_thinking_settings(self, config: AiLlmConfig, settings: dict[str, Any]) -> None:
        """按供应商差异写入 Pydantic AI 支持的 thinking 参数。"""

        provider_key = self._resolve_provider_key(config)
        adapter_mode = self._resolve_thinking_mode(provider_key, self._resolve_protocol_key(config))
        if adapter_mode == AiThinkingMode.NONE.value:
            return

        legacy_enabled = bool(getattr(config, "thinking_enabled", False))
        reasoning_mode = str(getattr(config, "reasoning_mode", "") or (AiReasoningMode.ENABLED.value if legacy_enabled else AiReasoningMode.AUTO.value))
        level = str(getattr(config, "reasoning_level", "") or getattr(config, "thinking_effort", "") or "medium").strip()
        capability = self._resolve_capability(config)
        effective = capability.effective_reasoning(reasoning_mode, level)
        native = effective.get("native_value")
        if reasoning_mode == AiReasoningMode.AUTO.value:
            return
        enabled = reasoning_mode == AiReasoningMode.ENABLED.value
        if enabled and not capability.profile.supports_reasoning:
            return
        if adapter_mode == AiThinkingMode.OPENAI_REASONING.value:
            settings.setdefault("openai_reasoning_effort", native if enabled else "none")
            return
        if adapter_mode == AiThinkingMode.OPENROUTER_REASONING.value:
            settings.setdefault("openrouter_reasoning", {"effort": native if enabled else "none"})
            return
        if adapter_mode == AiThinkingMode.GOOGLE_THINKING_LEVEL.value:
            if enabled and native:
                settings.setdefault("google_thinking_config", {"thinking_level": str(native).upper(), "include_thoughts": True})
            return
        if adapter_mode == AiThinkingMode.OLLAMA_THINK.value:
            self._merge_extra_body(settings, {"think": native if enabled else False})
            return
        if adapter_mode == AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value:
            body: dict[str, Any] = {"enable_thinking": enabled}
            if enabled:
                body["thinking_budget"] = int(getattr(config, "_reasoning_budget_tokens", None) or native or DASHSCOPE_THINKING_BUDGETS["medium"])
            self._merge_extra_body(settings, body)
            return
        if adapter_mode == AiThinkingMode.OPENAI_EXTRA_BODY_THINKING.value:
            body = {"thinking": {"type": "enabled" if enabled else "disabled"}}
            self._merge_extra_body(settings, body)
            if enabled and provider_key == "deepseek" and native:
                settings.setdefault("openai_reasoning_effort", str(native))

    def _resolve_capability(self, config: AiLlmConfig):
        """优先从配置或 Run 快照恢复能力，旧快照再回退到当前目录。"""

        snapshot = getattr(config, "model_capability_json", None)
        restored = capability_from_snapshot(snapshot if isinstance(snapshot, dict) else {})
        if restored is not None:
            return restored
        provider_key = self._resolve_provider_key(config)
        entry = get_llm_provider_entry(provider_key)
        return resolve_model_capability(
            provider_key,
            str(config.model_id),
            default_context_window_tokens=entry.default_context_window_tokens,
            default_model_max_output_tokens=entry.default_max_output_tokens,
            default_supports_image_input=entry.default_supports_image_input,
        )

    @staticmethod
    def _get_provider_config(config: AiLlmConfig):
        """读取模型关联的供应商配置，避免运行时误用未加载关系。"""

        provider_config = getattr(config, "provider_config", None)
        if provider_config is None:
            raise AppException(status_code=500, code="AI_LLM_PROVIDER_CONFIG_MISSING", detail="大模型配置缺少供应商配置。")
        return provider_config

    def _resolve_provider_key(self, config: AiLlmConfig) -> str:
        """读取模型关联供应商键值。"""

        return str(self._get_provider_config(config).provider_key or "").strip()

    def _resolve_protocol_key(self, config: AiLlmConfig) -> str:
        """读取服务端固化的调用协议，用户不能通过高级参数覆盖。"""

        provider_config = self._get_provider_config(config)
        return str(getattr(config, "protocol_key", "") or getattr(provider_config, "protocol_key", "") or "").strip()

    @staticmethod
    def _merge_extra_body(settings: dict[str, Any], patch: dict[str, Any]) -> None:
        """把平台派生的 extra_body 合并进高级配置，避免覆盖用户自定义字段。"""

        current = settings.get("extra_body")
        if isinstance(current, dict):
            merged = {**current, **patch}
        else:
            merged = dict(patch)
        settings["extra_body"] = merged

    @staticmethod
    def _normalize_deepseek_effort(effort: str) -> str:
        """把旧 UI 可输入值压缩成 DeepSeek 当前使用的 high/max 档位。"""

        if effort in {"xhigh", "max"}:
            return "max"
        return "high"

    @staticmethod
    def _resolve_thinking_mode(provider_key: str, protocol_key: str = "") -> str:
        """返回 provider 对应的 thinking 映射模式。"""

        if protocol_key == "google_chat" or provider_key == "google":
            return AiThinkingMode.GOOGLE_THINKING_LEVEL.value
        if protocol_key == "ollama_openai_compatible" or provider_key == "ollama":
            return AiThinkingMode.OLLAMA_THINK.value
        if protocol_key == "alibaba_openai_compatible" or provider_key == "dashscope":
            return AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value
        if protocol_key in {"deepseek_openai_compatible", "xiaomi_openai_compatible"} or provider_key in {"deepseek", "mimo"}:
            return AiThinkingMode.OPENAI_EXTRA_BODY_THINKING.value
        if protocol_key == "openrouter_chat" or provider_key == "openrouter":
            return AiThinkingMode.OPENROUTER_REASONING.value
        if protocol_key in {"openai_chat", "openai_compatible_chat"} or provider_key in {"openai", "openai_like", "nvidia"}:
            return AiThinkingMode.OPENAI_REASONING.value
        return AiThinkingMode.NONE.value
