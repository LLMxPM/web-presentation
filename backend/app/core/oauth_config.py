"""文件功能：校验默认关闭的远程 MCP OAuth 配置，发行地址只能来自显式部署配置。"""

from urllib.parse import urlsplit

from app.services.oauth.policy import OAuthPolicy


def resolve_oauth_policy(settings) -> OAuthPolicy | None:
    """启用时要求完整 HTTPS 边界及安全 Cookie；禁用时不对外提供协议端点。"""
    if not settings.oauth_enabled:
        return None
    policy = OAuthPolicy(
        issuer=settings.oauth_issuer,
        mcp_resource=settings.oauth_mcp_resource,
        api_audience=settings.oauth_api_audience,
    )
    for address in (policy.issuer, settings.oauth_editor_origin):
        parsed = urlsplit(address)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("首批 OAuth issuer 和 Editor origin 必须为不带路径的 HTTPS origin。")
    if not settings.session_secure:
        raise ValueError("启用 OAuth 必须设置 SESSION_SECURE=true。")
    if (
        settings.oauth_editor_origin != policy.issuer
        and settings.oauth_editor_origin not in settings.cors_origins
    ):
        raise ValueError("独立 Editor origin 必须显式加入 CORS_ORIGINS。")
    return policy
