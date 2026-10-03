"""文件功能：记录 OAuth 公共身份审计事件，字段中不允许携带令牌或协议原始请求。"""

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime


class OAuthAuditEvent(Base):
    """独立保留期审计；不使用动态 payload，避免原始凭证意外落库。"""

    __tablename__ = "oauth_audit_events"

    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    grant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    token_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
