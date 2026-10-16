"""文件功能：统一业务写接口的受信浏览器来源判定，并拒绝非受信源站借用会话发起 CSRF。"""

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings


def _origin(value: str) -> str:
    """规范化配置或浏览器请求中的 origin，不信任客户端 Host 来扩大白名单。

    统一按小写比较：浏览器发送的 Origin 恒为小写，配置侧大小写差异不应造成误拒。
    """
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.netloc}".lower() if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def trusted_business_origins() -> set[str]:
    """返回平台受信的浏览器来源集合：业务公开基址与 CORS 白名单的并集。

    Web 控制台（含 PAT 管理接口）与全局 CSRF 中间件共用同一份来源定义，
    避免两处白名单各自维护后出现"一边放行、一边拒绝"的行为分裂。
    """

    settings = get_settings()
    origins = {_origin(settings.backend_public_base_url), *(_origin(item) for item in settings.cors_origins)}
    origins.discard("")
    return origins


async def enforce_business_origin(request: Request, call_next):
    """校验浏览器写入的 Origin/Referer；无浏览器来源头的内部服务与 PAT 客户端保持原鉴权。"""
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        allowed = trusted_business_origins()
        supplied = request.headers.get("origin")
        if supplied is None and request.headers.get("referer"):
            supplied = _origin(request.headers["referer"])
        invalid = supplied is not None and _origin(supplied) not in allowed
        missing = supplied is None and request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}
        if invalid or missing:
            expected = "、".join(sorted(allowed)) or "平台未配置公开地址"
            return JSONResponse(
                {
                    "code": "UNTRUSTED_BUSINESS_ORIGIN",
                    "detail": f"该浏览器来源无权调用业务写接口，请通过平台公开地址访问（受信来源：{expected}）。",
                },
                status_code=403, headers={"Cache-Control": "no-store"},
            )
    response = await call_next(request)
    if request.url.path.startswith(("/api/", "/preview/", "/internal/", "/build-artifacts/")):
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"
        elif request.method not in {"GET", "HEAD", "OPTIONS"}:
            response.headers.setdefault("Cache-Control", "no-store")
    return response
