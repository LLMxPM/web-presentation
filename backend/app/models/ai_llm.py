"""文件功能：定义用户级大模型供应商配置、模型配置与固定槽位绑定的数据模型。"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AiLlmConfigScope, AiLlmSlot, AiModelType, AiReasoningMode, RecordStatus
from app.models.mixins import AuditMixin, TimestampMixin


class AiLlmProviderConfig(TimestampMixin, AuditMixin, Base):
    """用户可复用的聊天模型供应商凭证配置。"""

    __tablename__ = "ai_chat_provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    catalog_provider_key: Mapped[str | None] = mapped_column(
        ForeignKey("ai_chat_provider_catalog.provider_key"), nullable=True, index=True
    )
    protocol_key: Mapped[str] = mapped_column(String(64), nullable=False, default="openai_compatible_chat", index=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value, index=True)

    user = relationship("User", back_populates="llm_provider_configs")
    llm_configs: Mapped[list["AiLlmConfig"]] = relationship(back_populates="provider_config")


class AiLlmConfig(TimestampMixin, AuditMixin, Base):
    """用户可管理的聊天模型配置；旧类名仅供内部运行链路平滑迁移。"""

    __tablename__ = "ai_chat_model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default=AiLlmConfigScope.PERSONAL.value, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_config_id: Mapped[int] = mapped_column(ForeignKey("ai_chat_provider_configs.id"), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    model_type: Mapped[str] = mapped_column(String(32), nullable=False, default=AiModelType.CHAT.value, index=True)
    supports_image_input: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    context_window_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=128_000)
    history_token_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    advanced_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    model_capability_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capability_override_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    catalog_provider_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    catalog_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value, index=True)

    user = relationship("User", back_populates="llm_configs")
    provider_config: Mapped[AiLlmProviderConfig] = relationship(back_populates="llm_configs")
    slot_bindings: Mapped[list["AiLlmSlotBinding"]] = relationship(back_populates="llm_config")

    @property
    def reasoning_mode(self) -> str:
        """返回当前 Run 临时附着的推理模式，模型配置本身不持久化策略。"""

        return getattr(self, "_runtime_reasoning_mode", AiReasoningMode.AUTO.value)

    @reasoning_mode.setter
    def reasoning_mode(self, value: str) -> None:
        """仅在当前 ORM 对象上保存 Run 推理模式。"""

        self._runtime_reasoning_mode = str(value or AiReasoningMode.AUTO.value)

    @property
    def reasoning_level(self) -> str | None:
        """返回当前 Run 临时附着的推理强度。"""

        return getattr(self, "_runtime_reasoning_level", None)

    @reasoning_level.setter
    def reasoning_level(self, value: str | None) -> None:
        """仅在当前 ORM 对象上保存 Run 推理强度。"""

        self._runtime_reasoning_level = str(value) if value is not None else None

    @property
    def thinking_enabled(self) -> bool:
        """兼容运行器旧属性；真实策略仅属于当前 Run。"""

        return self.reasoning_mode == "enabled"

    @thinking_enabled.setter
    def thinking_enabled(self, value: bool) -> None:
        """把旧开关写入转换为 enabled/auto。"""

        self.reasoning_mode = "enabled" if value else "auto"

    @property
    def thinking_effort(self) -> str | None:
        """兼容旧 Python 调用方读取推理强度。"""

        return self.reasoning_level

    @thinking_effort.setter
    def thinking_effort(self, value: str | None) -> None:
        """把旧强度写入转换为平台四档。"""

        normalized = str(value or "").strip().lower()
        self.reasoning_level = "max" if normalized in {"xhigh", "max", "ultra"} else "low" if normalized == "minimal" else normalized or None

class AiLlmSlotBinding(TimestampMixin, AuditMixin, Base):
    """记录聊天槽位绑定及其独立运行策略。"""

    __tablename__ = "ai_chat_slot_bindings"
    __table_args__ = (
        Index(
            "uq_ai_chat_slot_bindings_personal_user_slot",
            "user_id",
            "slot",
            unique=True,
            sqlite_where=text("scope = 'personal'"),
            postgresql_where=text("scope = 'personal'"),
        ),
        Index(
            "uq_ai_chat_slot_bindings_global_slot",
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
    llm_config_id: Mapped[int | None] = mapped_column(ForeignKey("ai_chat_model_configs.id"), nullable=True, index=True)
    user = relationship("User", back_populates="llm_slot_bindings")
    llm_config: Mapped[AiLlmConfig | None] = relationship(back_populates="slot_bindings")


# 新代码使用 Chat 语义命名；旧名字保留为同一 ORM 类的内部兼容别名。
AiChatProviderConfig = AiLlmProviderConfig
AiChatModelConfig = AiLlmConfig
AiChatSlotBinding = AiLlmSlotBinding
