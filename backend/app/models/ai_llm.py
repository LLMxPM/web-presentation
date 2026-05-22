"""文件功能：定义用户级大模型配置与固定槽位绑定的数据模型。"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AiLlmConfigScope, AiLlmSlot, RecordStatus
from app.models.mixins import AuditMixin, TimestampMixin


class AiLlmConfig(TimestampMixin, AuditMixin, Base):
    """用户可管理的单个大模型配置。"""

    __tablename__ = "ai_llm_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    thinking_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thinking_effort: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supports_image_input: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    context_window_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=128_000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=32_000)
    history_token_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    compression_target_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    advanced_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value, index=True)

    user = relationship("User", back_populates="llm_configs")
    slot_bindings: Mapped[list["AiLlmSlotBinding"]] = relationship(back_populates="llm_config")


class AiLlmSlotBinding(TimestampMixin, AuditMixin, Base):
    """记录某个用户在固定槽位上绑定的模型配置。"""

    __tablename__ = "ai_llm_slot_bindings"
    __table_args__ = (
        Index(
            "uq_ai_llm_slot_bindings_personal_user_slot",
            "user_id",
            "slot",
            unique=True,
            sqlite_where=text("scope = 'personal'"),
            postgresql_where=text("scope = 'personal'"),
        ),
        Index(
            "uq_ai_llm_slot_bindings_global_slot",
            "slot",
            unique=True,
            sqlite_where=text("scope = 'global'"),
            postgresql_where=text("scope = 'global'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    slot: Mapped[str] = mapped_column(String(64), nullable=False, default=AiLlmSlot.AGENT_COORDINATOR.value)
    llm_config_id: Mapped[int | None] = mapped_column(ForeignKey("ai_llm_configs.id"), nullable=True, index=True)

    user = relationship("User", back_populates="llm_slot_bindings")
    llm_config: Mapped[AiLlmConfig | None] = relationship(back_populates="slot_bindings")
