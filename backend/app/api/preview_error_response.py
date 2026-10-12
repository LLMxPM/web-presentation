"""文件功能：为浏览器预览入口生成安全的错误文档和宿主通知，保留机器请求的 JSON 错误契约。"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from html import escape
from typing import Any
from urllib.parse import urlsplit

import jwt
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.token_service import TokenService


class PreviewDocumentRoute(APIRoute):
    """只在公开预览入口处理文档错误，避免改变普通 API 的异常响应。"""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """包裹本路由的鉴权、代理与缺失参数错误；非 HTML 请求继续交给原异常处理器。"""

        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            """按请求载体返回错误文档，保留原 HTTP 状态码。"""

            try:
                return await handler(request)
            except (AppException, HTTPException, RequestValidationError) as exc:
                if not accepts_preview_html(request):
                    raise
                if isinstance(exc, RequestValidationError):
                    status_code = 422
                    code = "PREVIEW_CONTEXT_REQUIRED"
                else:
                    status_code = exc.status_code
                    code = exc.code if isinstance(exc, AppException) else str(exc.detail)
                return preview_error_document(
                    request, artifact_id=str(request.path_params.get("artifact_id") or ""),
                    token=request.query_params.get("token", ""), status_code=status_code, code=code,
                )

        return handle


def accepts_preview_html(request: Request) -> bool:
    """只为明确接受 HTML 且优先级不低于 JSON 的请求返回文档；通配符默认保留 JSON。"""

    priorities: dict[str, float] = {}
    for item in request.headers.get("accept", "").lower().split(","):
        media_type, *parameters = item.strip().split(";")
        quality = 1.0
        for parameter in parameters:
            if parameter.strip().startswith("q="):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0.0
        priorities[media_type] = max(priorities.get(media_type, 0.0), quality)
    html_quality = max(priorities.get("text/html", 0.0), priorities.get("application/xhtml+xml", 0.0))
    return html_quality > 0 and html_quality >= priorities.get("application/json", 0.0)


def preview_error_document(
    request: Request, *, artifact_id: str, token: str, status_code: int, code: str,
) -> HTMLResponse:
    """生成无凭证错误页；过期票据仅在再次验签后用于工作台导航，不能用于续签或授权。"""

    claims: dict[str, object] = {}
    expired = False
    try:
        claims = TokenService.verify_preview_context_token(token)
    except jwt.ExpiredSignatureError:
        try:
            claims = TokenService.verify_preview_context_token(token, verify_exp=False)
            expired = True
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    if str(claims.get("artifact_id") or "") != artifact_id:
        claims = {}
        expired = False

    invalid = code in {"PREVIEW_CONTEXT_INVALID", "PREVIEW_CONTEXT_REQUIRED", "ARTIFACT_NOT_FOUND"}
    title = "预览链接已过期" if expired else "预览链接已失效" if invalid else "预览暂时无法打开"
    message = "请返回工作台重新生成预览。" if invalid else "请稍后重试；如仍无法打开，可返回工作台重新生成预览。"
    workspace_url = preview_workbench_url(request, claims)
    payload = _serialize_script({"version": 1, "artifactId": artifact_id, "code": code, "message": f"{title}，{message}"})
    retry_link = "" if invalid else '<button type="button" onclick="window.location.reload()">重试加载</button>'
    body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#f8fafc; color:#0f172a;
font:14px/1.7 system-ui,"Microsoft YaHei",sans-serif; }}
main {{ box-sizing:border-box; width:min(100% - 32px,520px); padding:32px; border:1px solid #e2e8f0;
border-radius:12px; background:white; }} h1 {{ font-size:22px; margin:0 0 12px; }} p {{ color:#475569; }}
.actions {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:24px; }} a,button {{ padding:8px 16px;
border:1px solid #cbd5e1; border-radius:6px; background:white; color:inherit; font:inherit; cursor:pointer; text-decoration:none; }}
a {{ background:#0f172a; color:white; }} a:focus-visible,button:focus-visible {{ outline:2px solid #2563eb; outline-offset:3px; }}
small {{ display:block; margin-top:20px; color:#64748b; overflow-wrap:anywhere; }}
</style></head><body><main><h1>{escape(title)}</h1><p>{escape(message)}</p>
<div class="actions"><a href="{escape(workspace_url, quote=True)}" target="_top">返回工作台</a>{retry_link}</div>
<small>错误码：{escape(code)}</small></main><script>
if (window.parent !== window) {{
  const payload = {payload};
  for (const type of ['page-preview:error', 'component-preview:error']) {{
    window.parent.postMessage({{ type, payload }}, '*');
  }}
}}
</script></body></html>"""
    return HTMLResponse(body, status_code=status_code, headers={
        "Cache-Control": "no-store", "Vary": "Accept", "Referrer-Policy": "no-referrer",
    })


def preview_workbench_url(request: Request, claims: dict[str, object]) -> str:
    """从服务端公开地址与 CORS 白名单选择 Editor 来源，不接受任意回跳地址。"""

    settings = get_settings()
    public_origin = _origin(settings.backend_public_base_url)
    allowed = [origin for item in settings.cors_origins if (origin := _origin(item))]
    referer_origin = _origin(request.headers.get("referer", ""))
    if referer_origin in allowed:
        origin = referer_origin
    elif public_origin in allowed:
        origin = public_origin
    else:
        same_host = [item for item in allowed if urlsplit(item).hostname == urlsplit(public_origin).hostname]
        remote = [item for item in allowed if urlsplit(item).hostname not in {"localhost", "127.0.0.1", "::1"}]
        origin = next(iter(same_host or remote or allowed), public_origin)
    workspace_id = str(claims.get("workspace_id") or "")
    project_id = str(claims.get("project_id") or "")
    if workspace_id.isdigit() and project_id.isdigit() and claims.get("scope_type") == "project":
        return f"{origin}/workspaces/{workspace_id}/projects/{project_id}/pages"
    if workspace_id.isdigit():
        return f"{origin}/workspaces/{workspace_id}/home"
    return f"{origin}/"


def _origin(value: str) -> str:
    """只保留 HTTP(S) 来源，丢弃路径、查询串和用户信息。"""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _serialize_script(value: object) -> str:
    """转义内联脚本的 JSON，避免路径或错误信息闭合 script 标签。"""

    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
