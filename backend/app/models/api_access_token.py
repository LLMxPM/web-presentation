"""文件功能：定义个人访问令牌（PAT）及关联的工作空间授权与 Scope 权限范围模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class ApiAccessToken(TimestampMixin, Base):
    """个人访问令牌（PAT）主表模型，仅在 Web 控制台创建与管理。"""

    __tablename__ = "api_access_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    token_public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped["User"] = relationship()
    workspaces: Mapped[list["ApiAccessTokenWorkspace"]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )
    scopes: Mapped[list["ApiAccessTokenScope"]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """判断当前访问令牌是否处于未吊销且未过期状态。"""
        from app.core.time_utils import normalize_utc, utc_now

        now = utc_now()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and normalize_utc(self.expires_at) <= now:
            return False
        return True


class ApiAccessTokenWorkspace(Base):
    """个人访问令牌与工作空间的授权绑定关系表。"""

    __tablename__ = "api_access_token_workspaces"

    token_id: Mapped[int] = mapped_column(
        ForeignKey("api_access_tokens.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    token: Mapped["ApiAccessToken"] = relationship(back_populates="workspaces")
    workspace: Mapped["Workspace"] = relationship()


class ApiAccessTokenScope(Base):
    """个人访问令牌细粒度权限 Scope 绑定表。"""

    __tablename__ = "api_access_token_scopes"

    token_id: Mapped[int] = mapped_column(
        ForeignKey("api_access_tokens.id", ondelete="CASCADE"), primary_key=True
    )
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)

    token: Mapped["ApiAccessToken"] = relationship(back_populates="scopes")
