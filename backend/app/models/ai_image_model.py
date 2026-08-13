"""文件功能：定义与聊天模型完全隔离的图片供应商、模型和槽位绑定。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AiLlmConfigScope, AiLlmSlot, RecordStatus
from app.models.mixins import AuditMixin, TimestampMixin


class AiImageProviderConfig(TimestampMixin, AuditMixin, Base):
    """图片供应商独立凭证配置。"""

    __tablename__ = "ai_image_provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value, index=True)

    models: Mapped[list["AiImageModelConfig"]] = relationship(back_populates="provider_config")


class AiImageModelConfig(TimestampMixin, AuditMixin, Base):
    """图片模型参数配置，能力由图片注册表校验。"""

    __tablename__ = "ai_image_model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_config_id: Mapped[int] = mapped_column(ForeignKey("ai_image_provider_configs.id"), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    advanced_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value, index=True)

    provider_config: Mapped[AiImageProviderConfig] = relationship(back_populates="models")
    slot_bindings: Mapped[list["AiImageSlotBinding"]] = relationship(back_populates="model_config")


class AiImageSlotBinding(TimestampMixin, AuditMixin, Base):
    """图片生成槽位绑定。"""

    __tablename__ = "ai_image_slot_bindings"
    __table_args__ = (
        Index(
            "uq_ai_image_slot_bindings_personal_user_slot",
            "user_id",
            "slot",
            unique=True,
            sqlite_where=text("scope = 'personal'"),
            postgresql_where=text("scope = 'personal'"),
        ),
        Index(
            "uq_ai_image_slot_bindings_global_slot",
            "slot",
            unique=True,
            sqlite_where=text("scope = 'global'"),
            postgresql_where=text("scope = 'global'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False, default=AiLlmSlot.IMAGE_GENERATION.value)
    model_config_id: Mapped[int | None] = mapped_column(ForeignKey("ai_image_model_configs.id"), nullable=True, index=True)

    model_config: Mapped[AiImageModelConfig | None] = relationship(back_populates="slot_bindings")
