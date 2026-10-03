"""文件功能：适配 Authlib 同步授权服务器，每请求独立暂存发行意图，提交由异步服务负责。"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256

from authlib.oauth2.rfc6749 import AuthorizationServer
from authlib.oauth2.rfc6749.errors import (
    InvalidClientError,
    InvalidGrantError,
    InvalidRequestError,
    OAuth2Error,
)
from authlib.oauth2.rfc6749.util import extract_basic_authorization

from app.core.time_utils import utc_now
from app.services.oauth.grants import (
    McpAuthorizationCodeGrant,
    McpRefreshTokenGrant,
    S256Challenge,
)
from app.services.oauth.request import ProtocolRequest
from app.services.oauth.resource_protocol import (
    EXCHANGE_GRANT_TYPE,
    McpIntrospectionEndpoint,
    McpRevocationEndpoint,
    McpTokenExchangeGrant,
)
from app.services.oauth.snapshots import ClientSnapshot, CredentialSnapshot
from app.services.oauth.token_snapshot import TokenSnapshot


def credential_digest(raw: str) -> str:
    """对高熵随机凭证做 SHA256；原始值不得持久化。"""
    return sha256(raw.encode("utf-8")).hexdigest()


class RedactedToken(dict):
    """保留真实响应字典，屏蔽 Authlib DEBUG 日志中的令牌 repr。"""

    def __repr__(self) -> str:
        """不让库的日志输出 access/refresh 原文。"""
        return "OAuthToken(<redacted>)"


@dataclass(frozen=True, slots=True)
class ProtocolResponse:
    """尚未交付的协议响应；只有持久化服务能决定成功响应是否可发送。"""

    status_code: int
    body: dict | str = field(repr=False)
    headers: tuple[tuple[str, str], ...] = field(repr=False)


class McpAuthorizationServer(AuthorizationServer):
    """仅限单请求的协议核，不持有数据库 Session 或可变全局用户身份。"""

    def __init__(
        self,
        *,
        client: ClientSnapshot | None,
        credential: CredentialSnapshot | None = None,
        now: datetime | None = None,
        access_ttl_seconds: int = 900,
        resource_token: TokenSnapshot | None = None,
        delegated_ttl_seconds: int = 60,
    ) -> None:
        """注册成熟协议实现，传入异步层准备的权限快照与可测试时钟。"""
        super().__init__(scopes_supported=sorted(client.scopes) if client else [])
        self.client_snapshot = client
        self.credential_snapshot = credential
        self.now = now or utc_now()
        self.access_ttl_seconds = access_ttl_seconds
        self.resource_token = resource_token
        self.delegated_ttl_seconds = delegated_ttl_seconds
        self.pending_revocation: str | None = None
        self.pending_code: str | None = None
        self.pending_token: RedactedToken | None = None
        self.consumed_hash: str | None = None
        self.replayed_refresh_hash: str | None = None
        self.register_grant(McpAuthorizationCodeGrant, [S256Challenge(required=True)])
        self.register_grant(McpRefreshTokenGrant)
        self.register_grant(McpTokenExchangeGrant)
        self.register_endpoint(McpIntrospectionEndpoint)
        self.register_endpoint(McpRevocationEndpoint)
        self.register_token_generator("default", self._generate_token)

    def query_client(self, client_id: str) -> ClientSnapshot | None:
        """只允许读取本请求预验证的注册客户端。"""
        client = self.client_snapshot
        return (
            client
            if client and hmac.compare_digest(client.client_id, client_id)
            else None
        )

    def match_credential(
        self, raw: str, client: ClientSnapshot
    ) -> CredentialSnapshot | None:
        """同时匹配摘要、客户端和到期时间；撤销状态由数据库预读层过滤。"""
        credential = self.credential_snapshot
        if credential is None or credential.expires_at <= self.now:
            return None
        if not credential.check_client(client):
            return None
        if not hmac.compare_digest(credential_digest(raw), credential.credential_hash):
            return None
        return credential

    def _generate_token(self, **kwargs) -> RedactedToken:
        """生成只返回一次的不透明凭证；发行期限由持久化层进一步收紧。"""
        exchanging = kwargs.get("grant_type") == EXCHANGE_GRANT_TYPE
        ttl = self.access_ttl_seconds
        if exchanging:
            ttl = min(
                self.delegated_ttl_seconds,
                int((self.resource_token.expires_at - self.now).total_seconds()),
            )
            if ttl <= 0:
                raise InvalidGrantError()
        token = RedactedToken(
            token_type="Bearer",
            access_token=("wp_dlg_" if exchanging else "wp_oat_")
            + secrets.token_urlsafe(48),
            expires_in=ttl,
            scope=kwargs.get("scope") or "",
        )
        if kwargs.get("include_refresh_token"):
            token["refresh_token"] = "wp_ort_" + secrets.token_urlsafe(48)
        return token

    def save_token(self, token: RedactedToken, request: ProtocolRequest) -> None:
        """只登记发行结果；不得在同步协议核内提交数据库。"""
        self.pending_token = token

    def create_oauth2_request(self, request: ProtocolRequest) -> ProtocolRequest:
        """要求 HTTP 层先完成异步读取，杜绝同步解析和 ORM 隐式 IO。"""
        if not isinstance(request, ProtocolRequest):
            raise TypeError("OAuth 请求必须由异步 HTTP 适配层准备。")
        return request

    def handle_response(self, status, body, headers) -> ProtocolResponse:
        """返回暂存结果而非 HTTP Response，让事务提交先于成功交付。"""
        return ProtocolResponse(status, body, tuple(headers))

    def send_signal(self, name: str, *args, **kwargs) -> None:
        """协议信号不记录原始请求；持久化审计由异步层提交。"""

    def token_response(self, request: ProtocolRequest) -> ProtocolResponse:
        """在派发前拒绝重复 grant_type/client_id 等参数，返回标准 OAuth 错误。"""
        try:
            self.validate_request(request)
        except OAuth2Error as error:
            return self.handle_error_response(request, error)
        return self.create_token_response(request)

    def validate_request(self, request: ProtocolRequest) -> None:
        """所有非交互端点统一拒绝重复参数、错误方法及混用客户端认证方式。"""
        request.payload.ensure_single_values()
        if len(request.headers.getlist("Authorization")) > 1:
            raise InvalidRequestError("Duplicate Authorization header.")
        if request.method != "POST":
            raise InvalidRequestError("POST is required.")
        if request.headers.get("Authorization"):
            client_id, _ = extract_basic_authorization(request.headers)
            if (
                self.client_snapshot is None
                or self.client_snapshot.auth_method != "client_secret_basic"
            ):
                raise InvalidClientError(status_code=401)
            if request.payload.client_id and request.payload.client_id != client_id:
                raise InvalidClientError(status_code=401)
            if request.payload.data.get("client_secret"):
                raise InvalidRequestError("Multiple client authentication methods.")

    def resource_response(
        self, endpoint: str, request: ProtocolRequest
    ) -> ProtocolResponse:
        """复用 Authlib 的自省/撤销标准错误与缓存头。"""
        try:
            self.validate_request(request)
        except OAuth2Error as error:
            return self.handle_error_response(request, error)
        return self.create_endpoint_response(endpoint, request)

    def match_resource_token(self, raw: str) -> TokenSnapshot | None:
        """只匹配异步查询得到的摘要，来源与有效期由具体端点进一步约束。"""
        token = self.resource_token
        if token and hmac.compare_digest(credential_digest(raw), token.token_hash):
            return token
        return None
