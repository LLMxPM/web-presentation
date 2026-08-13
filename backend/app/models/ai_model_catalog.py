"""文件功能：定义 Models.dev 聊天供应商、模型目录缓存与同步状态。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AiChatProviderCatalog(TimestampMixin, Base):
    """保存经过平台协议白名单过滤的 Models.dev 供应商。"""

    __tablename__ = "ai_chat_provider_catalog"

    provider_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    api_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    docs_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    npm_package: Mapped[str | None] = mapped_column(String(255), nullable=True)
    env_keys_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    protocol_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    models: Mapped[list["AiChatModelCatalog"]] = relationship(back_populates="provider")


class AiChatModelCatalog(TimestampMixin, Base):
    """保存 Models.dev 模型能力事实，用户配置只通过键值引用它。"""

    __tablename__ = "ai_chat_model_catalog"
    __table_args__ = (
        UniqueConstraint("provider_key", "model_id", name="uq_ai_chat_model_catalog_provider_model"),
        Index("ix_ai_chat_model_catalog_lookup", "provider_key", "is_current", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(
        ForeignKey("ai_chat_provider_catalog.provider_key"), nullable=False, index=True
    )
    model_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    release_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_updated: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_modalities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    output_modalities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    supports_tool_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_attachment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_reasoning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasoning_options_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    provider: Mapped[AiChatProviderCatalog] = relationship(back_populates="models")


class AiModelCatalogSyncState(Base):
    """记录目录版本、条件请求信息与跨进程租约。"""

    __tablename__ = "ai_model_catalog_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    etag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    catalog_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
