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
from app.ai.provider_catalog import MIMO_MAX_COMPLETION_TOKENS
from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_llm import AiLlmConfig
from app.models.enums import AiThinkingMode, RecordStatus

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
            raise AppException(status_code=409, code="AI_LLM_CONFIG_DISABLED", detail="当前大模型配置已归档。")
        provider_key = str(config.provider_key or "").strip()
        model_id = str(config.model_id or "").strip()
        api_key = self._cipher.decrypt(config.api_key_ciphertext)
        base_url = str(config.base_url or "").strip() or None

        if not model_id:
            raise AppException(status_code=400, code="AI_LLM_MODEL_ID_REQUIRED", detail="当前大模型配置缺少模型 ID。")

        http_client = build_llm_http_trace_client(config)

        if provider_key == "google":
            return GoogleModel(model_id, provider=GoogleProvider(api_key=api_key or None, http_client=http_client))
        if provider_key == "openrouter":
            return OpenRouterModel(model_id, provider=OpenRouterProvider(api_key=api_key or None, http_client=http_client))
        if provider_key == "ollama":
            return OpenAIChatModel(
                model_id,
                provider=OllamaProvider(base_url=base_url or "http://localhost:11434/v1", http_client=http_client),
            )
        if provider_key == "dashscope":
            return OpenAIChatModel(
                model_id,
                provider=AlibabaProvider(api_key=api_key or None, base_url=base_url, http_client=http_client),
            )
        if provider_key == "deepseek":
            return OpenAIChatModel(model_id, provider=DeepSeekProvider(api_key=api_key or None, http_client=http_client))
        if provider_key in {"openai", "openai_like", "nvidia", "mimo"}:
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
        if config.max_output_tokens:
            settings.setdefault("max_tokens", config.max_output_tokens)
        self._apply_provider_limits(config, settings)
        self._apply_thinking_settings(config, settings)
        return settings

    def _apply_provider_limits(self, config: AiLlmConfig, settings: dict[str, Any]) -> None:
        """按供应商硬限制修正运行参数，避免已保存旧配置持续触发模型 400。"""

        if config.provider_key != "mimo":
            return
        max_tokens = settings.get("max_tokens")
        if not isinstance(max_tokens, int) or max_tokens <= MIMO_MAX_COMPLETION_TOKENS:
            return
        settings["max_tokens"] = MIMO_MAX_COMPLETION_TOKENS

    def _apply_thinking_settings(self, config: AiLlmConfig, settings: dict[str, Any]) -> None:
        """按供应商差异写入 Pydantic AI 支持的 thinking 参数。"""

        mode = self._resolve_thinking_mode(config.provider_key)
        if mode == AiThinkingMode.NONE.value:
            return

        enabled = bool(config.thinking_enabled)
        effort = str(config.thinking_effort or "").strip()
        if mode == AiThinkingMode.OPENAI_REASONING.value:
            if enabled and effort:
                settings.setdefault("openai_reasoning_effort", effort)
            return
        if mode == AiThinkingMode.OPENROUTER_REASONING.value:
            if enabled and effort:
                settings.setdefault("openrouter_reasoning", {"effort": effort})
            return
        if mode == AiThinkingMode.GOOGLE_THINKING_LEVEL.value:
            if enabled and effort:
                settings.setdefault("google_thinking_config", {"thinking_level": effort.upper(), "include_thoughts": True})
            return
        if mode == AiThinkingMode.OLLAMA_THINK.value:
            if enabled and effort:
                self._merge_extra_body(settings, {"think": effort})
            return
        if mode == AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value:
            body: dict[str, Any] = {"enable_thinking": enabled}
            if enabled:
                body["thinking_budget"] = DASHSCOPE_THINKING_BUDGETS.get(effort, DASHSCOPE_THINKING_BUDGETS["medium"])
            self._merge_extra_body(settings, body)
            return
        if mode == AiThinkingMode.OPENAI_EXTRA_BODY_THINKING.value:
            body = {"thinking": {"type": "enabled" if enabled else "disabled"}}
            self._merge_extra_body(settings, body)
            if enabled and config.provider_key == "deepseek" and effort:
                settings.setdefault("openai_reasoning_effort", self._normalize_deepseek_effort(effort))

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
    def _resolve_thinking_mode(provider_key: str) -> str:
        """返回 provider 对应的 thinking 映射模式。"""

        if provider_key == "google":
            return AiThinkingMode.GOOGLE_THINKING_LEVEL.value
        if provider_key == "ollama":
            return AiThinkingMode.OLLAMA_THINK.value
        if provider_key == "dashscope":
            return AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value
        if provider_key in {"deepseek", "mimo"}:
            return AiThinkingMode.OPENAI_EXTRA_BODY_THINKING.value
        if provider_key == "openrouter":
            return AiThinkingMode.OPENROUTER_REASONING.value
        if provider_key in {"openai", "openai_like", "nvidia"}:
            return AiThinkingMode.OPENAI_REASONING.value
        return AiThinkingMode.NONE.value
