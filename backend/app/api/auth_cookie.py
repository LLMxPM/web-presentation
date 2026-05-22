"""文件功能：集中封装平台用户会话 Cookie 写入规则。"""

from fastapi import Response

from app.core.config import get_settings


def set_user_session_cookie(response: Response, token: str) -> None:
    """写入用户会话 Cookie，并使用当前配置刷新浏览器端有效期。"""

    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_secure,
        path="/",
    )
