"""文件功能：约束显式 OAuth 信任地址和首期凭证期限，不从请求 Host 推导发行身份。"""

from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_CREDENTIAL_RETENTION_SECONDS = 7 * 24 * 60 * 60
MAX_AUDIT_RETENTION_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class OAuthPolicy:
    """显式部署边界；不能从 HTTP Host 或转发 Header 推导。"""

    issuer: str
    mcp_resource: str
    api_audience: str
    code_ttl_seconds: int = 60
    access_ttl_seconds: int = 900
    delegated_ttl_seconds: int = 60
    consent_ttl_seconds: int = 600
    refresh_lifetime_seconds: int = 30 * 24 * 60 * 60
    credential_retention_seconds: int = MAX_CREDENTIAL_RETENTION_SECONDS
    audit_retention_seconds: int = MAX_AUDIT_RETENTION_SECONDS

    def __post_init__(self) -> None:
        """拒绝相同 audience、不受信地址和越过首期上限的期限。"""
        for address in (self.issuer, self.mcp_resource, self.api_audience):
            parsed = urlsplit(address)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "OAuth 信任地址必须为明确的 HTTPS 地址，不能含凭证、查询或片段。"
                )
        if self.mcp_resource == self.api_audience:
            raise ValueError("MCP resource 与 API audience 必须不同。")
        limits = (
            (self.code_ttl_seconds, 60),
            (self.access_ttl_seconds, 900),
            (self.delegated_ttl_seconds, 60),
            (self.consent_ttl_seconds, 600),
            (self.refresh_lifetime_seconds, 30 * 24 * 60 * 60),
            (self.credential_retention_seconds, MAX_CREDENTIAL_RETENTION_SECONDS),
            (self.audit_retention_seconds, MAX_AUDIT_RETENTION_SECONDS),
        )
        if any(
            type(value) is not int or value <= 0 or value > upper
            for value, upper in limits
        ):
            raise ValueError("OAuth 期限必须为正数且不得超过首期上限。")
