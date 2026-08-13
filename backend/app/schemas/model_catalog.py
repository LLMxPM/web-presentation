"""文件功能：定义聊天模型目录查询与同步状态接口。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import SchemaBase


class ChatProviderCatalogItem(SchemaBase):
    """前端可选择的 Models.dev 聊天供应商。"""

    provider_key: str
    name: str
    api_url: str | None = None
    docs_url: str | None = None
    default_base_url: str | None = None
    protocol_key: str
    catalog_version: str
    synced_at: str | None = None


class ChatModelCatalogItem(SchemaBase):
    """单个聊天模型的目录能力事实。"""

    provider_key: str
    model_id: str
    name: str
    family: str | None = None
    status: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    context_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    supports_tool_call: bool = False
    supports_structured_output: bool = False
    supports_attachment: bool = False
    supports_reasoning: bool = False
    reasoning_options: dict[str, Any] = Field(default_factory=dict)
    catalog_version: str
    synced_at: str | None = None


class ModelCatalogSyncItem(SchemaBase):
    """目录同步可观测状态。"""

    catalog_version: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    syncing: bool = False
