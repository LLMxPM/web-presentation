"""文件功能：定义拆分后的聊天模型、图片模型及绑定策略接口。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AiLlmConfigScope
from app.schemas.common import SchemaBase


class ReasoningPolicy(BaseModel):
    """单次聊天 Run 的推理策略。"""

    mode: Literal["auto", "disabled", "effort", "budget_tokens"] = "auto"
    value: str | int | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "ReasoningPolicy":
        """约束需要值的模式，自动和关闭模式不携带值。"""

        if self.mode in {"auto", "disabled"} and self.value is not None:
            raise ValueError("auto/disabled 推理策略不能包含 value。")
        if self.mode == "effort" and not isinstance(self.value, str):
            raise ValueError("effort 推理策略必须提供字符串 value。")
        if self.mode == "budget_tokens" and (not isinstance(self.value, int) or self.value <= 0):
            raise ValueError("budget_tokens 推理策略必须提供正整数 value。")
        return self


class ChatProviderConfigCreate(BaseModel):
    """创建聊天供应商连接。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    catalog_provider_key: str | None = Field(default=None, max_length=128)
    custom: bool = False
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_identity(self) -> "ChatProviderConfigCreate":
        """目录供应商与自定义供应商二选一，自定义必须提供 Base URL。"""

        if self.custom == bool(self.catalog_provider_key):
            raise ValueError("必须选择一个目录供应商，或创建自定义 OpenAI-compatible 供应商。")
        if self.custom and not str(self.base_url or "").strip():
            raise ValueError("自定义供应商必须填写 Base URL。")
        return self


class ChatProviderConfigUpdate(BaseModel):
    """更新聊天供应商连接；供应商身份和协议不可修改。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)
    status: Literal["active", "archived"] | None = None


class ChatProviderConfigItem(SchemaBase):
    """聊天供应商连接响应。"""

    id: int
    scope: str
    editable: bool
    name: str
    provider_key: str
    catalog_provider_key: str | None = None
    provider_name: str
    protocol_key: str
    base_url: str | None = None
    has_api_key: bool
    api_key_masked: str | None = None
    status: str


class ChatModelConfigCreate(BaseModel):
    """创建聊天模型配置。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    provider_config_id: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=255)
    capability_override: dict[str, Any] = Field(default_factory=dict)
    advanced_config: dict[str, Any] = Field(default_factory=dict)


class ChatModelConfigUpdate(BaseModel):
    """更新聊天模型配置。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider_config_id: int | None = Field(default=None, ge=1)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    capability_override: dict[str, Any] | None = None
    advanced_config: dict[str, Any] | None = None
    status: Literal["active", "archived"] | None = None


class ChatModelConfigItem(SchemaBase):
    """聊天模型及合并后能力。"""

    id: int
    scope: str
    editable: bool
    name: str
    provider_config_id: int
    provider_name: str
    provider_key: str
    protocol_key: str
    model_id: str
    catalog_version: str | None = None
    capability: dict[str, Any]
    capability_override: dict[str, Any]
    advanced_config: dict[str, Any]
    status: str


class ChatBindingUpdate(BaseModel):
    """更新聊天槽位模型；运行策略在发起会话时选择。"""

    model_config = ConfigDict(extra="forbid")

    model_config_id: int | None = Field(default=None, ge=1)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL


class ChatBindingItem(SchemaBase):
    """聊天槽位绑定状态。"""

    slot: str
    model_config_id: int | None = None
    model_name: str | None = None
    provider_config_id: int | None = None
    provider_config_name: str | None = None
    provider_key: str | None = None
    provider_name: str | None = None
    model_id: str | None = None
    supports_image_input: bool = False
    binding_ready: bool
    inherited_from_global: bool = False


class ImageProviderCatalogItem(SchemaBase):
    """代码注册的图片供应商和模型。"""

    provider_key: str
    name: str
    docs_url: str
    default_base_url: str | None = None
    requires_base_url: bool
    models: list[dict[str, Any]]


class ImageProviderConfigCreate(BaseModel):
    """创建图片供应商连接。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    provider_key: str = Field(min_length=1, max_length=64)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)


class ImageProviderConfigUpdate(BaseModel):
    """更新图片供应商连接。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)
    status: Literal["active", "archived"] | None = None


class ImageProviderConfigItem(SchemaBase):
    """图片供应商连接响应。"""

    id: int
    scope: str
    editable: bool
    name: str
    provider_key: str
    provider_name: str
    base_url: str | None = None
    has_api_key: bool
    api_key_masked: str | None = None
    status: str


class ImageModelConfigCreate(BaseModel):
    """创建图片模型配置。"""

    name: str = Field(min_length=1, max_length=128)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL
    provider_config_id: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=255)
    advanced_config: dict[str, Any] = Field(default_factory=dict)


class ImageModelConfigUpdate(BaseModel):
    """更新图片模型配置。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider_config_id: int | None = Field(default=None, ge=1)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    advanced_config: dict[str, Any] | None = None
    status: Literal["active", "archived"] | None = None


class ImageModelConfigItem(SchemaBase):
    """图片模型配置响应。"""

    id: int
    scope: str
    editable: bool
    name: str
    provider_config_id: int
    provider_name: str
    provider_key: str
    model_id: str
    capability: dict[str, Any]
    advanced_config: dict[str, Any]
    status: str


class ImageBindingUpdate(BaseModel):
    """更新图片生成槽位。"""

    model_config_id: int | None = Field(default=None, ge=1)
    scope: AiLlmConfigScope = AiLlmConfigScope.PERSONAL


class ImageBindingItem(SchemaBase):
    """图片生成槽位绑定状态。"""

    slot: str = "image_generation"
    model_config_id: int | None = None
    model_name: str | None = None
    provider_config_id: int | None = None
    provider_config_name: str | None = None
    provider_key: str | None = None
    provider_name: str | None = None
    model_id: str | None = None
    binding_ready: bool
    inherited_from_global: bool = False
