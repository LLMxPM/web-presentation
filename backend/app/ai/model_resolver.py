"""文件功能：按供应商目录把用户配置解析为可执行的 Agno 模型实例。"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from app.ai.provider_catalog import (
    PROTECTED_ADVANCED_CONFIG_KEYS,
    get_llm_provider_entry,
)
from app.ai.secret_cipher import LlmSecretCipher
from app.core.exceptions import AppException
from app.models.ai_llm import AiLlmConfig
from app.models.enums import AiThinkingMode, RecordStatus

_DEEPSEEK_THINKING_TIMEOUT_SECONDS = 1200.0
_DEEPSEEK_THINKING_STREAM_RETRIES = 1
_DEEPSEEK_THINKING_RETRY_DELAY_SECONDS = 3
_DASHSCOPE_THINKING_BUDGET_BY_EFFORT = {
    "low": 2000,
    "medium": 5000,
    "high": 10000,
}


class LlmModelResolver:
    """把数据库中的用户模型配置翻译成 Agno 模型对象。"""

    def __init__(self) -> None:
        self._cipher = LlmSecretCipher()

    def resolve_model(self, config: AiLlmConfig) -> Any:
        """根据单条用户模型配置生成可供 Agent 使用的 model。"""

        if config.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=409, code="AI_LLM_CONFIG_DISABLED", detail="当前大模型配置已归档。")

        entry = get_llm_provider_entry(config.provider_key)
        advanced_config = self._validate_advanced_config(config.advanced_config_json or {})
        api_key = self._cipher.decrypt(config.api_key_ciphertext)

        kwargs: dict[str, Any] = {}
        kwargs.update(advanced_config)
        kwargs["id"] = config.model_id

        if entry.supports_api_key and api_key:
            kwargs["api_key"] = api_key

        if config.base_url:
            if not entry.supports_base_url:
                raise AppException(
                    status_code=400,
                    code="AI_LLM_BASE_URL_UNSUPPORTED",
                    detail="当前供应商不支持自定义 Base URL。",
                )
            if config.provider_key == "ollama":
                kwargs["host"] = config.base_url
            else:
                kwargs["base_url"] = config.base_url

        thinking_effort = self._resolve_thinking_effort(
            config.thinking_effort,
            default_effort=entry.default_thinking_effort,
        )
        self._apply_provider_defaults(entry.provider_key, kwargs, thinking_enabled=config.thinking_enabled)
        self._apply_thinking(
            entry.thinking_mode,
            kwargs,
            config.thinking_enabled,
            provider_key=entry.provider_key,
            thinking_effort=thinking_effort,
        )

        try:
            model_class = self._load_model_class(entry.agno_class_path)
        except ImportError as exc:
            raise AppException(
                status_code=500,
                code="AI_LLM_PROVIDER_DEPENDENCY_MISSING",
                detail=f"供应商依赖未安装：{entry.label}。",
            ) from exc

        try:
            return model_class(**kwargs)
        except TypeError as exc:
            raise AppException(
                status_code=400,
                code="AI_LLM_PROVIDER_ARGS_INVALID",
                detail=f"供应商参数不合法：{entry.label}。",
            ) from exc

    @staticmethod
    def _load_model_class(class_path: str) -> type[Any]:
        """按完整类路径导入 Agno 模型类。"""

        module_name, _, class_name = class_path.rpartition(".")
        module = import_module(module_name)
        return getattr(module, class_name)

    @staticmethod
    def _validate_advanced_config(value: dict[str, Any]) -> dict[str, Any]:
        """校验高级 JSON 配置仅包含允许的扩展字段。"""

        if not isinstance(value, dict):
            raise AppException(status_code=400, code="AI_LLM_ADVANCED_CONFIG_INVALID", detail="高级配置必须是 JSON 对象。")
        conflicted_keys = sorted(key for key in value if key in PROTECTED_ADVANCED_CONFIG_KEYS)
        if conflicted_keys:
            raise AppException(
                status_code=400,
                code="AI_LLM_ADVANCED_CONFIG_CONFLICT",
                detail=f"高级配置禁止覆盖受管字段：{', '.join(conflicted_keys)}。",
            )
        return dict(value)

    @staticmethod
    def _apply_provider_defaults(provider_key: str, kwargs: dict[str, Any], *, thinking_enabled: bool) -> None:
        """按供应商补齐稳态默认值；用户高级配置拥有更高优先级。"""

        if provider_key != "deepseek" or not thinking_enabled:
            return

        kwargs.setdefault("timeout", _DEEPSEEK_THINKING_TIMEOUT_SECONDS)
        kwargs.setdefault("retries", _DEEPSEEK_THINKING_STREAM_RETRIES)
        kwargs.setdefault("delay_between_retries", _DEEPSEEK_THINKING_RETRY_DELAY_SECONDS)
        kwargs.setdefault("exponential_backoff", True)

    @staticmethod
    def _resolve_thinking_effort(
        value: str | None,
        *,
        default_effort: str | None,
    ) -> str | None:
        """归一化运行时思考强度，保留供应商未来扩展值。"""

        normalized = str(value or "").strip().lower() or default_effort
        return normalized or None

    @staticmethod
    def _apply_thinking(
        thinking_mode: str,
        kwargs: dict[str, Any],
        enabled: bool,
        *,
        provider_key: str,
        thinking_effort: str | None,
    ) -> None:
        """按供应商映射规则把 thinking_enabled 翻译为实际参数。"""

        if thinking_mode == AiThinkingMode.NONE.value:
            return
        if thinking_mode == AiThinkingMode.OPENAI_REASONING.value:
            if provider_key == "deepseek":
                extra_body = dict(kwargs.get("extra_body") or {})
                thinking = dict(extra_body.get("thinking") or {})
                thinking["type"] = "enabled" if enabled else "disabled"
                extra_body["thinking"] = thinking
                kwargs["extra_body"] = extra_body
            if not enabled:
                return
            default_effort = thinking_effort or ("high" if provider_key == "deepseek" else "medium")
            kwargs.setdefault("reasoning_effort", kwargs.pop("reasoning_effort", default_effort))
            return
        if not enabled:
            return
        if thinking_mode == AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value:
            kwargs["enable_thinking"] = True
            if thinking_effort:
                kwargs.setdefault(
                    "thinking_budget",
                    _DASHSCOPE_THINKING_BUDGET_BY_EFFORT.get(thinking_effort, 5000),
                )
            return
        if thinking_mode == AiThinkingMode.OLLAMA_THINK.value:
            request_params = dict(kwargs.get("request_params") or {})
            request_params.setdefault("think", thinking_effort or True)
            kwargs["request_params"] = request_params
            return
        if thinking_mode == AiThinkingMode.GOOGLE_THINKING_LEVEL.value:
            if thinking_effort:
                kwargs.setdefault("thinking_level", thinking_effort)
