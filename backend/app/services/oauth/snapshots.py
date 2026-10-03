"""文件功能：定义 Authlib 同步协议核使用的不可变快照，避免同步钩子访问异步数据库。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from authlib.oauth2.rfc6749.errors import InvalidScopeError

from app.core.security import verify_password


@dataclass(frozen=True, slots=True)
class ClientSnapshot:
    """仅由数据库验证器提供的已注册客户端；密钥哈希不参与日志表示。"""

    client_id: str
    redirect_uris: tuple[str, ...]
    scopes: frozenset[str]
    resource: str
    auth_method: str = "none"
    secret_hash: str | None = field(default=None, repr=False)
    kind: str = "client"
    api_audience: str | None = None

    def get_client_id(self) -> str:
        """返回公共客户端标识。"""
        return self.client_id

    def get_default_redirect_uri(self) -> None:
        """要求客户端显式指定回调，不选择隐式默认值。"""
        return

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        """只允许已登记 URI 的精确匹配，不做前缀或通配比较。"""
        return redirect_uri in self.redirect_uris

    def get_allowed_scope(self, scope: str | None) -> str:
        """拒绝空权限与范围扩张，不静默裁剪客户端请求。"""
        requested = frozenset((scope or "").split())
        if not requested or not requested <= self.scopes:
            raise InvalidScopeError()
        return " ".join(sorted(requested))

    def check_client_secret(self, client_secret: str) -> bool:
        """复用平台密码哈希验证机密客户端，公开客户端没有伪造密钥。"""
        return bool(
            self.secret_hash and verify_password(client_secret, self.secret_hash)
        )

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        """客户端只管理自身授权，服务只允许自省与受控交换。"""
        endpoints = (
            {"token", "introspection"}
            if self.kind == "service"
            else {"token", "revocation"}
        )
        return endpoint in endpoints and method == self.auth_method

    def check_response_type(self, response_type: str) -> bool:
        """首期仅支持授权码流程。"""
        return self.kind == "client" and response_type == "code"

    def check_grant_type(self, grant_type: str) -> bool:
        """服务没有用户授权码或刷新能力，只允许明确的交换 grant。"""
        if self.kind == "service":
            return grant_type == "urn:ietf:params:oauth:grant-type:token-exchange"
        return grant_type in {"authorization_code", "refresh_token"}


@dataclass(frozen=True, slots=True)
class CredentialSnapshot:
    """数据库查询后得到的授权码或刷新快照；只保存凭证摘要。"""

    credential_hash: str = field(repr=False)
    grant_id: str
    client_id: str
    user_id: int
    resource: str
    scopes: frozenset[str]
    expires_at: datetime
    consumed: bool = False
    redirect_uri: str | None = None
    code_challenge: str | None = field(default=None, repr=False)
    code_challenge_method: str | None = None
    family_id: str | None = None

    def get_redirect_uri(self) -> str | None:
        """提供授权码绑定的原始回调 URI。"""
        return self.redirect_uri

    def get_scope(self) -> str:
        """返回本次凭证的权限上限，不继承客户端更大的范围。"""
        return " ".join(sorted(self.scopes))

    def check_client(self, client: ClientSnapshot) -> bool:
        """刷新凭证必须属于完成认证的原客户端。"""
        return client.client_id == self.client_id
