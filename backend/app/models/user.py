"""文件功能：定义平台用户、用户会话与登录态相关数据模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RecordStatus, UserRole
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    """平台用户模型，支持平台管理员与普通工作空间用户。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=UserRole.WORKSPACE_USER.value)
    status: Mapped[RecordStatus] = mapped_column(String(32), nullable=False, default=RecordStatus.ACTIVE.value)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preview_size_presets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")
    llm_configs: Mapped[list["AiLlmConfig"]] = relationship(back_populates="user")
    llm_slot_bindings: Mapped[list["AiLlmSlotBinding"]] = relationship(back_populates="user")
    agent_configs: Mapped[list["AiAgentUserConfig"]] = relationship(back_populates="user")
    agent_tool_configs: Mapped[list["AiAgentToolUserConfig"]] = relationship(back_populates="user")


class UserSession(TimestampMixin, Base):
    """用户登录会话模型，用于支撑 Cookie 鉴权与会话失效控制。"""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped[User] = relationship(back_populates="sessions")
