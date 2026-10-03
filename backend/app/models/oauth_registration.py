"""文件功能：定义预注册 OAuth 客户端及 MCP 服务身份，不保存原始密钥。"""

from sqlalchemy import Boolean, CheckConstraint, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONPayload
from app.models.mixins import TimestampMixin


class OAuthClient(TimestampMixin, Base):
    """用户授权客户端，回调、权限与资源必须预先登记。"""

    __tablename__ = "oauth_clients"
    __table_args__ = (
        CheckConstraint(
            "auth_method IN ('none', 'client_secret_basic')",
            name="ck_oauth_client_auth_method",
        ),
    )

    client_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONPayload, nullable=False)
    resource: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class OAuthMcpService(TimestampMixin, Base):
    """只允许对明确 MCP resource 自省并交换到指定 API audience 的服务身份。"""

    __tablename__ = "oauth_mcp_services"

    service_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(String(512), nullable=False)
    api_audience: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
