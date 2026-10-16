"""文件功能：拒绝非受信浏览器源站调用业务写接口，防止预览子域借用会话发起 CSRF。"""

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings


def _origin(value: str) -> str:
    """规范化配置或浏览器请求中的 origin，不信任客户端 Host 来扩大白名单。"""
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme in {"http", "https"} and parsed.netloc else ""


async def enforce_business_origin(request: Request, call_next):
    """校验浏览器写入的 Origin/Referer；无浏览器来源头的内部服务与 PAT 客户端保持原鉴权。"""
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        settings = get_settings()
        allowed = {_origin(settings.backend_public_base_url), *(_origin(item) for item in settings.cors_origins)}
        allowed.discard("")
        supplied = request.headers.get("origin")
        if supplied is None and request.headers.get("referer"):
            supplied = _origin(request.headers["referer"])
        invalid = supplied is not None and _origin(supplied) not in allowed
        missing = supplied is None and request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}
        if invalid or missing:
            return JSONResponse(
                {"code": "UNTRUSTED_BUSINESS_ORIGIN", "detail": "该浏览器源站无权调用业务写接口。"},
                status_code=403, headers={"Cache-Control": "no-store"},
            )
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/preview/", "/internal/", "/build-artifacts/")):
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
        elif request.method not in {"GET", "HEAD", "OPTIONS"}:
            response.headers.setdefault("Cache-Control", "no-store")
    return response
