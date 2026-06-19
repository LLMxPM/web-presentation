"""文件功能：维护可归一化的大模型供应商目录与固定槽位元数据。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AppException
from app.models.enums import AiLlmSlot, AiThinkingMode

OPENAI_DOCS_URL = "https://pydantic.dev/docs/ai/models/openai/"
OPENROUTER_DOCS_URL = "https://pydantic.dev/docs/ai/models/openrouter/"
DASHSCOPE_DOCS_URL = "https://pydantic.dev/docs/ai/models/openai/"
OPENAI_LIKE_DOCS_URL = "https://pydantic.dev/docs/ai/models/openai/"
GOOGLE_DOCS_URL = "https://pydantic.dev/docs/ai/models/google/"
DEEPSEEK_DOCS_URL = "https://pydantic.dev/docs/ai/models/openai/"
OLLAMA_DOCS_URL = "https://pydantic.dev/docs/ai/models/ollama/"
NVIDIA_DOCS_URL = "https://pydantic.dev/docs/ai/models/openai/"
MIMO_DOCS_URL = "https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call"


@dataclass(slots=True, frozen=True)
class LlmProviderCatalogEntry:
    """描述一个可供用户选择的 Pydantic AI 模型供应商。"""

    provider_key: str
    label: str
    provider_adapter: str
    docs_url: str
    supports_base_url: bool
    supports_api_key: bool
    supports_thinking: bool
    thinking_mode: str
    default_base_url: str | None = None
    default_model_id: str | None = None
    default_thinking_enabled: bool = False
    default_thinking_effort: str | None = None
    default_context_window_tokens: int | None = None
    default_max_output_tokens: int | None = None
    default_supports_image_input: bool = False
    thinking_effort_options: tuple[str, ...] = ()
    advanced_json_hint: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class LlmSlotDefinition:
    """描述一个固定的大模型槽位。"""

    slot: str
    label: str


PROTECTED_ADVANCED_CONFIG_KEYS = {
    "id",
    "name",
    "provider",
    "api_key",
    "base_url",
    "client",
    "async_client",
    "http_client",
    "host",
}

LLM_SLOT_DEFINITIONS: dict[str, LlmSlotDefinition] = {
    AiLlmSlot.AGENT_COORDINATOR.value: LlmSlotDefinition(
        slot=AiLlmSlot.AGENT_COORDINATOR.value,
        label="总控智能体",
    ),
    AiLlmSlot.COMPONENT_MANAGER.value: LlmSlotDefinition(
        slot=AiLlmSlot.COMPONENT_MANAGER.value,
        label="组件助手",
    ),
    AiLlmSlot.RESOURCE_MANAGER.value: LlmSlotDefinition(
        slot=AiLlmSlot.RESOURCE_MANAGER.value,
        label="资源助手",
    ),
}

LLM_PROVIDER_CATALOG: dict[str, LlmProviderCatalogEntry] = {
    "openai": LlmProviderCatalogEntry(
        provider_key="openai",
        label="OpenAI",
        provider_adapter="pydantic_ai.models.openai.OpenAIChatModel",
        docs_url=OPENAI_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_base_url="https://api.openai.com/v1",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "openrouter": LlmProviderCatalogEntry(
        provider_key="openrouter",
        label="OpenRouter",
        provider_adapter="pydantic_ai.models.openrouter.OpenRouterModel",
        docs_url=OPENROUTER_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENROUTER_REASONING.value,
        default_base_url="https://openrouter.ai/api/v1",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "dashscope": LlmProviderCatalogEntry(
        provider_key="dashscope",
        label="DashScope",
        provider_adapter="pydantic_ai.providers.alibaba.AlibabaProvider",
        docs_url=DASHSCOPE_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value,
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_model_id="qwen-plus",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "openai_like": LlmProviderCatalogEntry(
        provider_key="openai_like",
        label="OpenAILike",
        provider_adapter="pydantic_ai.providers.openai.OpenAIProvider",
        docs_url=OPENAI_LIKE_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "google": LlmProviderCatalogEntry(
        provider_key="google",
        label="Google",
        provider_adapter="pydantic_ai.models.google.GoogleModel",
        docs_url=GOOGLE_DOCS_URL,
        supports_base_url=False,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.GOOGLE_THINKING_LEVEL.value,
        default_model_id="gemini-flash-latest",
        default_thinking_effort="high",
        thinking_effort_options=("low", "high"),
    ),
    "deepseek": LlmProviderCatalogEntry(
        provider_key="deepseek",
        label="DeepSeek",
        provider_adapter="pydantic_ai.providers.deepseek.DeepSeekProvider",
        docs_url=DEEPSEEK_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_EXTRA_BODY_THINKING.value,
        default_base_url="https://api.deepseek.com",
        default_model_id="deepseek-v4-pro",
        default_thinking_enabled=True,
        default_thinking_effort="high",
        default_context_window_tokens=1_000_000,
        default_max_output_tokens=384_000,
        thinking_effort_options=("high", "max"),
    ),
    "ollama": LlmProviderCatalogEntry(
        provider_key="ollama",
        label="Ollama",
        provider_adapter="pydantic_ai.providers.ollama.OllamaProvider",
        docs_url=OLLAMA_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OLLAMA_THINK.value,
        default_base_url="http://localhost:11434",
        default_model_id="llama3.1",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "nvidia": LlmProviderCatalogEntry(
        provider_key="nvidia",
        label="NVIDIA",
        provider_adapter="pydantic_ai.providers.openai.OpenAIProvider",
        docs_url=NVIDIA_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_base_url="https://integrate.api.nvidia.com/v1",
        default_model_id="meta/llama-3.3-70b-instruct",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "mimo": LlmProviderCatalogEntry(
        provider_key="mimo",
        label="MiMo",
        provider_adapter="pydantic_ai.providers.openai.OpenAIProvider",
        docs_url=MIMO_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_EXTRA_BODY_THINKING.value,
        default_base_url="https://api.xiaomimimo.com/v1",
    ),
}


def list_llm_provider_entries() -> list[LlmProviderCatalogEntry]:
    """按标签排序返回所有可用供应商目录项。"""

    return sorted(LLM_PROVIDER_CATALOG.values(), key=lambda item: item.label.lower())


def get_llm_provider_entry(provider_key: str) -> LlmProviderCatalogEntry:
    """按 provider_key 查询供应商目录项。"""

    entry = LLM_PROVIDER_CATALOG.get(provider_key)
    if entry is None:
        raise AppException(status_code=400, code="AI_LLM_PROVIDER_UNSUPPORTED", detail="当前供应商暂不支持。")
    return entry


def get_llm_slot_definition(slot: str) -> LlmSlotDefinition:
    """按槽位值查询固定槽位定义。"""

    definition = LLM_SLOT_DEFINITIONS.get(slot)
    if definition is None:
        raise AppException(status_code=400, code="AI_LLM_SLOT_UNSUPPORTED", detail="当前槽位暂不支持。")
    return definition
