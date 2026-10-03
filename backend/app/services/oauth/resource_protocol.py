"""文件功能：适配 Authlib 自省/撤销扩展，并以其协议核实现受限的 RFC 8693 交换。"""

from authlib.oauth2.rfc6749.errors import (
    InvalidGrantError,
    InvalidRequestError,
    InvalidScopeError,
    UnauthorizedClientError,
)
from authlib.oauth2.rfc6749.grants import BaseGrant
from authlib.oauth2.rfc6749.grants.base import TokenEndpointMixin
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7662 import IntrospectionEndpoint

from app.schemas.oauth import OAuthActiveIntrospection

ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"


class McpIntrospectionEndpoint(IntrospectionEndpoint):
    """自省只面向受信 MCP 服务，用户客户端不能读取任意 Token 的身份。"""

    def query_token(self, token_string, token_type_hint):
        """只匹配本次异步层预读的 access 快照。"""
        return self.server.match_resource_token(token_string)

    def check_permission(self, token, client, request) -> bool:
        """服务必须绑定此 MCP resource，无法自省其他服务或 API audience。"""
        return (
            client.kind == "service"
            and token.kind == "access"
            and client.resource == token.audience
        )

    def introspect_token(self, token) -> dict:
        """返回版本化公开身份 DTO；不返回原始 Token 或客户端密钥。"""
        return OAuthActiveIntrospection(
            active=True,
            wp_version=1,
            token_type="Bearer",
            client_id=token.client_id,
            sub=str(token.user_id),
            aud=token.audience,
            iss=token.issuer,
            exp=int(token.expires_at.timestamp()),
            iat=int(token.created_at.timestamp()),
            jti=token.token_id,
            grant_id=token.grant_id,
            scope=" ".join(sorted(token.scopes)),
            workspace_ids=sorted(token.workspace_ids),
        ).model_dump()


class McpRevocationEndpoint(RevocationEndpoint):
    """原客户端撤销任一 access/refresh 时撤销整 Grant；未知凭证统一成功。"""

    CLIENT_AUTH_METHODS = ("none", "client_secret_basic")

    def query_token(self, token_string, token_type_hint):
        """预过滤归属，避免库的跨客户端错误暴露 Token 是否存在。"""
        token = self.server.match_resource_token(token_string)
        client = self.server.client_snapshot
        return token if token and client and token.check_client(client) else None

    def revoke_token(self, token, request) -> None:
        """只暂存撤销对象，异步层提交 Grant/家族撤销后才交付成功。"""
        self.server.pending_revocation = token.grant_id


class McpTokenExchangeGrant(BaseGrant, TokenEndpointMixin):
    """使用 Authlib 派发、Basic 认证和标准错误，领域层限定唯一 source/target。"""

    GRANT_TYPE = EXCHANGE_GRANT_TYPE
    TOKEN_ENDPOINT_AUTH_METHODS = ("client_secret_basic",)

    def validate_token_request(self) -> None:
        """只允许服务认证后的自身 MCP access 换固定 API audience，禁止扩权与转授。"""
        self.request.payload.ensure_single_values()
        client = self.authenticate_token_endpoint_client()
        self.request.client = client
        if client.kind != "service" or not client.check_grant_type(self.GRANT_TYPE):
            raise UnauthorizedClientError()
        data = self.request.payload.data
        allowed = {
            "grant_type",
            "client_id",
            "subject_token",
            "subject_token_type",
            "requested_token_type",
            "resource",
            "scope",
        }
        if set(data) - allowed:
            raise InvalidRequestError("Unsupported token exchange parameter.")
        if data.get("subject_token_type") != ACCESS_TOKEN_TYPE:
            raise InvalidRequestError("Invalid subject_token_type.")
        if data.get("requested_token_type", ACCESS_TOKEN_TYPE) != ACCESS_TOKEN_TYPE:
            raise InvalidRequestError("Invalid requested_token_type.")
        if data.get("resource") != client.api_audience:
            raise InvalidRequestError("Invalid target resource.")
        token = self.server.match_resource_token(data.get("subject_token", ""))
        if (
            token is None
            or not token.active
            or token.kind != "access"
            or token.audience != client.resource
            or token.is_expired()
        ):
            raise InvalidGrantError()
        scopes = frozenset(data["scope"].split()) if "scope" in data else token.scopes
        if not scopes or not scopes <= token.scopes:
            raise InvalidScopeError()
        self.request.scope = " ".join(sorted(scopes))
        self.request.user = token.user_id

    def create_token_response(self):
        """发行短期 delegated 意图，绝不发行 refresh；期限还受源 Token 限制。"""
        token = self.generate_token(
            user=self.request.user,
            scope=self.request.scope,
            include_refresh_token=False,
        )
        token["issued_token_type"] = ACCESS_TOKEN_TYPE
        self.save_token(token)
        return 200, token, self.TOKEN_RESPONSE_HEADER
