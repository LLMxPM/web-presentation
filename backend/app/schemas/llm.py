"""文件功能：定义大模型供应商目录、用户模型配置与槽位绑定的接口模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AiLlmConfigScope
from app.schemas.common import SchemaBase

LLM_CONTEXT_WINDOW_TOKEN_MAX = 2_000_000
LLM_MAX_OUTPUT_TOKEN_MAX = 2_000_000
LLM_CONTEXT_WINDOW_TOKEN_DEFAULT = 128_000
LLM_MAX_OUTPUT_TOKEN_DEFAULT = 32_000
LLM_COMPRESSION_TARGET_RATIO_DEFAULT = 0.1


class LlmProviderCatalogItem(SchemaBase):
    """返回给前端的供应商目录项。"""

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
    thinking_effort_options: list[str] = Field(default_factory=list)
    advanced_json_hint: dict[str, Any] = Field(default_factory=dict)


class LlmConfigItem(SchemaBase):
    """用户的大模型配置详情。"""

    id: int
    scope: AiLlmConfigScope
    owner_user_id: int | None = None
    editable: bool
    name: str
    provider_key: str
    provider_label: str
    model_id: str
    base_url: str | None = None
    thinking_enabled: bool
    thinking_effort: str | None = None
    supports_image_input: bool
    context_window_tokens: int
    max_output_tokens: int
    history_token_ratio: float
    compression_target_ratio: float
    advanced_config_json: dict[str, Any] = Field(default_factory=dict)
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
    provider_key: str | None = None
    provider_label: str | None = None
    model_id: str | None = None
    binding_ready: bool
    supports_image_input: bool = False
    inherited_from_global: bool = False


class LlmConfigCreateRequest(BaseModel):
    """创建大模型配置的请求体。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    provider_key: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)
    thinking_enabled: bool = False
    thinking_effort: str | None = Field(default=None, max_length=64)
    supports_image_input: bool = False
    context_window_tokens: int = Field(default=LLM_CONTEXT_WINDOW_TOKEN_DEFAULT, ge=1024, le=LLM_CONTEXT_WINDOW_TOKEN_MAX)
    max_output_tokens: int = Field(default=LLM_MAX_OUTPUT_TOKEN_DEFAULT, ge=256, le=LLM_MAX_OUTPUT_TOKEN_MAX)
    history_token_ratio: float = Field(default=0.5, ge=0.0, le=0.9)
    compression_target_ratio: float = Field(default=LLM_COMPRESSION_TARGET_RATIO_DEFAULT, ge=0.02, le=0.5)
    advanced_config_json: dict[str, Any] = Field(default_factory=dict)

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
    provider_key: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)
    thinking_enabled: bool | None = None
    thinking_effort: str | None = Field(default=None, max_length=64)
    supports_image_input: bool | None = None
    context_window_tokens: int | None = Field(default=None, ge=1024, le=LLM_CONTEXT_WINDOW_TOKEN_MAX)
    max_output_tokens: int | None = Field(default=None, ge=256, le=LLM_MAX_OUTPUT_TOKEN_MAX)
    history_token_ratio: float | None = Field(default=None, ge=0.0, le=0.9)
    compression_target_ratio: float | None = Field(default=None, ge=0.02, le=0.5)
    advanced_config_json: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(active|archived)$")

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
