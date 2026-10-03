"""文件功能：在 Authlib 授权码与刷新实现上约束 S256、精确 resource 和单次消费意图。"""

from authlib.oauth2.rfc6749.errors import (
    InvalidGrantError,
    InvalidRequestError,
    InvalidScopeError,
)
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc7636 import CodeChallenge

from app.services.oauth.snapshots import ClientSnapshot, CredentialSnapshot


class S256Challenge(CodeChallenge):
    """公开及机密客户端都必须使用显式 PKCE S256。"""

    SUPPORTED_CODE_CHALLENGE_METHOD = ("S256",)

    def validate_code_challenge(self, grant, redirect_uri) -> None:
        """补足库默认允许缺省 PKCE 的路径，随后复用库的格式验证。"""
        data = grant.request.payload.data
        if (
            not data.get("code_challenge")
            or data.get("code_challenge_method") != "S256"
        ):
            raise InvalidRequestError("PKCE S256 is required.")
        super().validate_code_challenge(grant, redirect_uri)


class McpAuthorizationCodeGrant(AuthorizationCodeGrant):
    """协议验证不产生数据库写；仅登记授权码消费和发行意图。"""

    TOKEN_ENDPOINT_AUTH_METHODS = ("none", "client_secret_basic")

    def validate_authorization_request(self) -> str:
        """复用 Authlib 回调/权限/PKCE 验证，强制显式且唯一的 MCP resource。"""
        self.request.payload.ensure_single_values()
        redirect_uri = super().validate_authorization_request()
        if self.request.payload.data.get("resource") != self.client.resource:
            raise InvalidRequestError("Invalid resource.")
        return redirect_uri

    def validate_consent_request(self) -> str:
        """授权页准备同样应用 resource 和 S256 约束。"""
        return self.validate_authorization_request()

    def save_authorization_code(self, code: str, request) -> None:
        """仅暂存待持久化授权码，不能在未提交事务时交付重定向。"""
        self.server.pending_code = code

    def query_authorization_code(self, code: str, client: ClientSnapshot):
        """只匹配数据库预读的当前客户端凭证；摘要比较由适配器负责。"""
        credential = self.server.match_credential(code, client)
        if credential is None or credential.consumed:
            return None
        return credential

    def validate_token_request(self) -> None:
        """先调用库完成客户端/回调/PKCE 校验，再检查授权码的资源及权限绑定。"""
        self.request.payload.ensure_single_values()
        super().validate_token_request()
        credential = self.request.authorization_code
        if self.request.payload.data.get("resource") != credential.resource:
            raise InvalidGrantError("Invalid resource.")
        requested = self.request.payload.scope
        if requested is not None and frozenset(requested.split()) != credential.scopes:
            raise InvalidScopeError()

    def authenticate_user(self, credential: CredentialSnapshot) -> int:
        """返回异步层已校验状态的用户标识。"""
        return credential.user_id

    def delete_authorization_code(self, credential: CredentialSnapshot) -> None:
        """声明一次消费，异步层必须 CAS 成功并提交后才能返回 Token。"""
        self.server.consumed_hash = credential.credential_hash


class McpRefreshTokenGrant(RefreshTokenGrant):
    """每次刷新发行新凭证；重放标志由持久化层处理为授权链撤销。"""

    TOKEN_ENDPOINT_AUTH_METHODS = ("none", "client_secret_basic")
    INCLUDE_NEW_REFRESH_TOKEN = True

    def validate_token_request(self) -> None:
        """复用库的客户端和 Scope 子集验证，再检查唯一的原始资源。"""
        self.request.payload.ensure_single_values()
        super().validate_token_request()
        if (
            self.request.payload.data.get("resource")
            != self.request.refresh_token.resource
        ):
            raise InvalidGrantError("Invalid resource.")

    def authenticate_refresh_token(self, refresh_token: str):
        """认证客户端后识别刷新重放；别的客户端不得借此撤销原授权。"""
        credential = self.server.match_credential(refresh_token, self.client)
        if credential and credential.consumed:
            self.server.replayed_refresh_hash = credential.credential_hash
            return None
        return credential

    def authenticate_user(self, credential: CredentialSnapshot) -> int:
        """返回预验证的用户标识，不在同步钩子内访问 ORM。"""
        return credential.user_id

    def revoke_old_credential(self, credential: CredentialSnapshot) -> None:
        """声明旧刷新凭证消费，异步事务同时写入下一代凭证。"""
        self.server.consumed_hash = credential.credential_hash
