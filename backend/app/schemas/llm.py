"""文件功能：定义大模型供应商目录、供应商配置、用户模型配置与槽位绑定的接口模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.ai.model_budget import (
    COMPRESSION_TARGET_TOKENS,
    CONTEXT_WINDOW_TOKEN_DEFAULT,
    CONTEXT_WINDOW_TOKEN_MAX,
    CONTEXT_WINDOW_TOKEN_MIN,
    derive_model_run_budget,
)
from app.models.enums import AiLlmConfigScope, AiModelType, AiReasoningLevel, AiReasoningMode
from app.schemas.common import SchemaBase

LLM_CONTEXT_WINDOW_TOKEN_MAX = CONTEXT_WINDOW_TOKEN_MAX
LLM_CONTEXT_WINDOW_TOKEN_MIN = CONTEXT_WINDOW_TOKEN_MIN
LLM_CONTEXT_WINDOW_TOKEN_DEFAULT = CONTEXT_WINDOW_TOKEN_DEFAULT
LLM_MAX_OUTPUT_TOKEN_DEFAULT = derive_model_run_budget(CONTEXT_WINDOW_TOKEN_DEFAULT).max_output_tokens
LLM_COMPRESSION_TARGET_TOKEN_DEFAULT = COMPRESSION_TARGET_TOKENS


class LlmProviderCatalogItem(SchemaBase):
    """返回给前端的供应商目录项。"""

    provider_key: str
    label: str
    provider_type: AiModelType
    provider_adapter: str
    docs_url: str
    supports_base_url: bool
    requires_base_url: bool = False
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
    supported_model_types: list[AiModelType] = Field(default_factory=lambda: [AiModelType.CHAT])
    default_image_generation_model_id: str | None = None
    base_url_hint: str | None = None
    thinking_effort_options: list[str] = Field(default_factory=list)
    advanced_json_hint: dict[str, Any] = Field(default_factory=dict)
    image_generation_models: list[dict[str, Any]] = Field(default_factory=list)


class LlmConfigItem(SchemaBase):
    """用户的大模型配置详情。"""

    id: int
    scope: AiLlmConfigScope
    owner_user_id: int | None = None
    editable: bool
    name: str
    provider_config_id: int
    provider_config_name: str
    provider_key: str
    provider_label: str
    model_id: str
    model_type: AiModelType = AiModelType.CHAT
    reasoning_mode: AiReasoningMode
    reasoning_level: AiReasoningLevel | None = None
    thinking_enabled: bool = Field(default=False, deprecated=True)
    thinking_effort: str | None = Field(default=None, deprecated=True)
    supports_image_input: bool
    context_window_tokens: int = Field(description="平台允许供应商请求使用的最大输入 tokens。")
    required_model_context_tokens: int
    request_output_tokens: int
    runtime_headroom_tokens: int
    compression_trigger_tokens: int
    compression_target_tokens: int
    budget_policy_version: str
    model_max_output_tokens: int = Field(deprecated=True)
    request_max_output_tokens: int = Field(deprecated=True)
    max_output_tokens: int = Field(deprecated=True)
    capability_source: str
    capability_verified: bool
    model_capability_json: dict[str, Any] = Field(default_factory=dict)
    effective_reasoning: dict[str, Any] = Field(default_factory=dict)
    history_token_ratio: float
    compression_target_ratio: float = Field(deprecated=True)
    advanced_config_json: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class LlmProviderConfigItem(SchemaBase):
    """用户可复用的大模型供应商配置详情。"""

    id: int
    scope: AiLlmConfigScope
    owner_user_id: int | None = None
    editable: bool
    name: str
    provider_key: str
    provider_label: str
    provider_type: AiModelType
    base_url: str | None = None
    status: str
    has_api_key: bool
    api_key_masked: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LlmSlotBindingItem(SchemaBase):
    """固定槽位与用户模型配置的绑定关系。"""

    slot: str
    slot_label: str
    llm_config_id: int | None = None
    llm_config_name: str | None = None
    provider_config_id: int | None = None
    provider_config_name: str | None = None
    provider_key: str | None = None
    provider_label: str | None = None
    model_id: str | None = None
    model_type: AiModelType | None = None
    binding_ready: bool
    supports_image_input: bool = False
    inherited_from_global: bool = False


class LlmConfigCreateRequest(BaseModel):
    """创建大模型配置的请求体。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    provider_config_id: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=255)
    model_type: AiModelType = AiModelType.CHAT
    reasoning_mode: AiReasoningMode | None = None
    reasoning_level: AiReasoningLevel | None = None
    thinking_enabled: bool | None = Field(default=None, deprecated=True)
    thinking_effort: str | None = Field(default=None, max_length=64, deprecated=True)
    supports_image_input: bool = False
    context_window_tokens: int | None = Field(default=None, ge=LLM_CONTEXT_WINDOW_TOKEN_MIN, le=LLM_CONTEXT_WINDOW_TOKEN_MAX, description="平台可用输入窗口 tokens；省略时采用能力解析建议值。")
    model_capability_override: dict[str, Any] | None = None
    advanced_config_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_reasoning_contract(self) -> "LlmConfigCreateRequest":
        """兼容旧字段并确保三态与四档组合有效。"""

        _normalize_reasoning_request(self)
        return self

    @field_validator("advanced_config_json")
    @classmethod
    def validate_advanced_config_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        """限制高级配置必须是 JSON object。"""

        if not isinstance(value, dict):
            raise ValueError("advanced_config_json 必须是 JSON 对象。")
        return value

class LlmConfigUpdateRequest(BaseModel):
    """更新大模型配置的请求体。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider_config_id: int | None = Field(default=None, ge=1)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    model_type: AiModelType | None = None
    reasoning_mode: AiReasoningMode | None = None
    reasoning_level: AiReasoningLevel | None = None
    thinking_enabled: bool | None = Field(default=None, deprecated=True)
    thinking_effort: str | None = Field(default=None, max_length=64, deprecated=True)
    supports_image_input: bool | None = None
    context_window_tokens: int | None = Field(default=None, ge=LLM_CONTEXT_WINDOW_TOKEN_MIN, le=LLM_CONTEXT_WINDOW_TOKEN_MAX, description="平台可用输入窗口 tokens。")
    model_capability_override: dict[str, Any] | None = None
    advanced_config_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(active|archived)$")

    @model_validator(mode="after")
    def normalize_reasoning_contract(self) -> "LlmConfigUpdateRequest":
        """兼容旧字段并拒绝新旧推理字段混用。"""

        _normalize_reasoning_request(self, partial=True)
        return self

    @field_validator("advanced_config_json")
    @classmethod
    def validate_advanced_config_json(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """限制高级配置必须是 JSON object。"""

        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("advanced_config_json 必须是 JSON 对象。")
        return value


class LlmSlotBindingUpdateRequest(BaseModel):
    """更新固定槽位绑定关系的请求体。"""

    llm_config_id: int | None = Field(default=None, ge=1)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL


class LlmProviderConfigCreateRequest(BaseModel):
    """创建供应商配置的请求体。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    provider_key: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)


class LlmProviderConfigUpdateRequest(BaseModel):
    """更新供应商配置的请求体；provider 与 scope 创建后不可变。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class LlmModelCapabilityResolveRequest(BaseModel):
    """请求解析指定供应商配置与模型 ID 的能力。"""

    provider_config_id: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=255)
    override: dict[str, Any] | None = None


class LlmModelCapabilityItem(SchemaBase):
    """返回模型能力、来源和平台四档的实际映射。"""

    source: str
    verified: bool
    profile_key: str
    profile_version: int
    context_window_tokens: int
    model_context_window_tokens: int | None = None
    model_max_output_tokens: int
    required_model_context_tokens: int
    request_output_tokens: int
    runtime_headroom_tokens: int
    compression_trigger_tokens: int
    compression_target_tokens: int
    budget_policy_version: str
    request_max_output_tokens: int = Field(deprecated=True)
    supports_image_input: bool
    supports_reasoning: bool
    supports_explicit_disable: bool
    default_level: str | None = None
    level_mapping: dict[str, str | int | None] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def _normalize_reasoning_request(value: Any, *, partial: bool = False) -> None:
    """把旧 thinking 字段转换为新契约，并拒绝同一请求混用两套字段。"""

    fields = value.model_fields_set
    uses_new = bool({"reasoning_mode", "reasoning_level"} & fields)
    uses_legacy = bool({"thinking_enabled", "thinking_effort"} & fields)
    if uses_new and uses_legacy:
        raise ValueError("reasoning_mode/reasoning_level 不能与旧 thinking 字段同时提交。")
    if uses_legacy:
        enabled = bool(value.__dict__.get("thinking_enabled"))
        effort = str(value.__dict__.get("thinking_effort") or "").strip().lower()
        if not enabled:
            value.reasoning_mode = AiReasoningMode.AUTO
            value.reasoning_level = None
        elif effort in {"none", "off", "disabled"}:
            value.reasoning_mode = AiReasoningMode.DISABLED
            value.reasoning_level = None
        else:
            value.reasoning_mode = AiReasoningMode.ENABLED
            normalized = "low" if effort == "minimal" else "max" if effort in {"xhigh", "max", "ultra"} else effort
            value.reasoning_level = AiReasoningLevel(normalized if normalized in {item.value for item in AiReasoningLevel} else "medium")
    elif not partial and value.reasoning_mode is None:
        value.reasoning_mode = AiReasoningMode.AUTO
    if value.reasoning_mode == AiReasoningMode.ENABLED and value.reasoning_level is None:
        value.reasoning_level = AiReasoningLevel.MEDIUM
    if value.reasoning_mode in {AiReasoningMode.AUTO, AiReasoningMode.DISABLED}:
        value.reasoning_level = None
