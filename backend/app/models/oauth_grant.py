"""文件功能：保存用户固定空间授权及刷新家族，提供撤销与发行共用的数据库围栏。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONPayload, UTCDateTime
from app.models.mixins import TimestampMixin


class OAuthGrant(TimestampMixin, Base):
    """具体空间集合授权，不支持未来空间；每次发行和撤销更新同一版本行。"""

    __tablename__ = "oauth_grants"

    grant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id"), nullable=False, index=True
    )
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    resource: Mapped[str] = mapped_column(String(512), nullable=False)
    workspace_ids: Mapped[list[int]] = mapped_column(JSONPayload, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OAuthRefreshFamily(Base):
    """刷新家族使用绝对期限，轮换不会无限延长用户授权会话。"""

    __tablename__ = "oauth_refresh_families"

    family_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_grants.grant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class OAuthConsentRequest(Base):
    """绑定登录会话和 CSRF 摘要的待确认请求；原始 Token 与授权码不入此表。"""

    __tablename__ = "oauth_consent_requests"

    request_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource: Mapped[str] = mapped_column(String(512), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(8), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
