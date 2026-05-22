"""文件功能：定义用户级智能体补充提示词与工具配置覆盖模型。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import AuditMixin, TimestampMixin


class AiAgentUserConfig(TimestampMixin, AuditMixin, Base):
    """保存某个用户对内置 Agent 描述与业务补充提示词的配置。"""

    __tablename__ = "ai_agent_user_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_ai_agent_user_configs_user_agent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="override")

    user = relationship("User", back_populates="agent_configs")


class AiAgentToolUserConfig(TimestampMixin, AuditMixin, Base):
    """保存某个用户对内置 Agent 工具开关与工具提示词的覆盖配置。"""

    __tablename__ = "ai_agent_tool_user_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", "tool_key", name="uq_ai_agent_tool_user_configs_user_tool"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="agent_tool_configs")
