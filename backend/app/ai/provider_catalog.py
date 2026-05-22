"""文件功能：维护可归一化的大模型供应商目录与固定槽位元数据。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AppException
from app.models.enums import AiLlmSlot, AiThinkingMode

OPENAI_DOCS_URL = "https://docs.agno.com/models/providers/native/openai/responses/overview"
OPENROUTER_DOCS_URL = "https://docs.agno.com/models/providers/gateways/openrouter/overview"
DASHSCOPE_DOCS_URL = "https://docs.agno.com/models/providers/native/dashscope/overview"
OPENAI_LIKE_DOCS_URL = "https://docs.agno.com/models/providers/openai-like"
GOOGLE_DOCS_URL = "https://docs.agno.com/models/providers/native/google/overview"
DEEPSEEK_DOCS_URL = "https://docs.agno.com/models/providers/native/deepseek/overview"
OLLAMA_DOCS_URL = "https://docs.agno.com/models/providers/local/ollama/overview"
NVIDIA_DOCS_URL = "https://docs.agno.com/reference/models/nvidia"


@dataclass(slots=True, frozen=True)
class LlmProviderCatalogEntry:
    """描述一个可供用户选择的 Agno 模型供应商。"""

    provider_key: str
    label: str
    agno_class_path: str
    docs_url: str
    supports_base_url: bool
    supports_api_key: bool
    supports_thinking: bool
    thinking_mode: str
    default_base_url: str | None = None
    default_thinking_effort: str | None = None
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
        agno_class_path="agno.models.openai.responses.OpenAIResponses",
        docs_url=OPENAI_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
        advanced_json_hint={"verbosity": "low"},
    ),
    "openrouter": LlmProviderCatalogEntry(
        provider_key="openrouter",
        label="OpenRouter",
        agno_class_path="agno.models.openrouter.openrouter.OpenRouter",
        docs_url=OPENROUTER_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_base_url="https://openrouter.ai/api/v1",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
        advanced_json_hint={"app_name": "web-presentation"},
    ),
    "dashscope": LlmProviderCatalogEntry(
        provider_key="dashscope",
        label="DashScope",
        agno_class_path="agno.models.dashscope.dashscope.DashScope",
        docs_url=DASHSCOPE_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.DASHSCOPE_ENABLE_THINKING.value,
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
    ),
    "openai_like": LlmProviderCatalogEntry(
        provider_key="openai_like",
        label="OpenAILike",
        agno_class_path="agno.models.openai.like.OpenAILike",
        docs_url=OPENAI_LIKE_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
        advanced_json_hint={"temperature": 0.2},
    ),
    "google": LlmProviderCatalogEntry(
        provider_key="google",
        label="Google",
        agno_class_path="agno.models.google.gemini.Gemini",
        docs_url=GOOGLE_DOCS_URL,
        supports_base_url=False,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.GOOGLE_THINKING_LEVEL.value,
        default_thinking_effort="high",
        thinking_effort_options=("low", "high"),
        advanced_json_hint={"temperature": 0.2},
    ),
    "deepseek": LlmProviderCatalogEntry(
        provider_key="deepseek",
        label="DeepSeek",
        agno_class_path="agno.models.deepseek.deepseek.DeepSeek",
        docs_url=DEEPSEEK_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_thinking_effort="high",
        thinking_effort_options=("low", "medium", "high"),
        advanced_json_hint={
            "timeout": 1200,
            "retries": 1,
            "delay_between_retries": 3,
            "exponential_backoff": True,
        },
    ),
    "ollama": LlmProviderCatalogEntry(
        provider_key="ollama",
        label="Ollama",
        agno_class_path="agno.models.ollama.Ollama",
        docs_url=OLLAMA_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OLLAMA_THINK.value,
        default_base_url="http://localhost:11434",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
        advanced_json_hint={"options": {"temperature": 0.2}},
    ),
    "nvidia": LlmProviderCatalogEntry(
        provider_key="nvidia",
        label="NVIDIA",
        agno_class_path="agno.models.nvidia.nvidia.Nvidia",
        docs_url=NVIDIA_DOCS_URL,
        supports_base_url=True,
        supports_api_key=True,
        supports_thinking=True,
        thinking_mode=AiThinkingMode.OPENAI_REASONING.value,
        default_base_url="https://integrate.api.nvidia.com/v1",
        default_thinking_effort="medium",
        thinking_effort_options=("low", "medium", "high"),
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
