"""文件功能：保存 OAuth 授权码及各类不透明凭证摘要、期限和来源链。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONPayload, UTCDateTime


class OAuthAuthorizationCode(Base):
    """一次性授权码，完整绑定客户端通过 Grant 指定，PKCE 与回调随码保存。"""

    __tablename__ = "oauth_authorization_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_grants.grant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    redirect_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(8), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class OAuthToken(Base):
    """Access/refresh/delegated 凭证仅存摘要，delegated 明确关联源 access 和服务。"""

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('access', 'refresh', 'delegated')", name="ck_oauth_token_kind"
        ),
        CheckConstraint(
            "kind != 'refresh' OR family_id IS NOT NULL", name="ck_oauth_refresh_family"
        ),
        CheckConstraint(
            "kind != 'delegated' OR (source_token_id IS NOT NULL AND service_id IS NOT NULL)",
            name="ck_oauth_delegated_source",
        ),
    )

    token_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_grants.grant_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    audience: Mapped[str] = mapped_column(String(512), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False)
    family_id: Mapped[str | None] = mapped_column(
        ForeignKey("oauth_refresh_families.family_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    parent_token_id: Mapped[str | None] = mapped_column(
        ForeignKey("oauth_tokens.token_id"), nullable=True
    )
    source_token_id: Mapped[str | None] = mapped_column(
        ForeignKey("oauth_tokens.token_id"), nullable=True
    )
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("oauth_mcp_services.service_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
