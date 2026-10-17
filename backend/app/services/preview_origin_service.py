"""文件功能：解析不携带业务 Cookie 的预览源站，并生成只包含可信桥接代码的预览宿主页。"""

from __future__ import annotations

import json
from html import escape
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.exceptions import AppException


def isolated_preview_base_url() -> str:
    """复用 Runtime 公开地址；本地同主机名自动使用 preview.localhost，远程同主机名拒绝执行。"""
    settings = get_settings()
    base = str(settings.runtime_public_base_url or settings.runtime_base_url).rstrip("/")
    parsed = urlsplit(base)
    business_hosts = {urlsplit(settings.backend_public_base_url).hostname}
    business_hosts.update(urlsplit(item).hostname for item in settings.cors_origins)
    if parsed.hostname in business_hosts:
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            authority = "preview.localhost" + (f":{parsed.port}" if parsed.port else "")
            return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))
        raise AppException(
            503, "PREVIEW_ORIGIN_NOT_ISOLATED",
            "RUNTIME_PUBLIC_BASE_URL 必须使用独立于工作台与 Backend 的预览主机名。",
            headers={"Cache-Control": "no-store"},
        )
    return base


def isolated_preview_origin() -> str:
    """返回私有构建使用的隔离源站根地址，不携带 Runtime 路径前缀。"""
    parsed = urlsplit(isolated_preview_base_url())
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def preview_shell(*, artifact_id: str, token: str, workbench_url: str, parameters: dict[str, str] | None = None) -> HTMLResponse:
    """在业务源站只运行固定桥接代码；用户源码始终在另一主机名的 iframe 中执行。"""
    base = isolated_preview_base_url()
    target = f"{base}/__preview?{urlencode({**(parameters or {}), 'token': token})}"
    target_origin = isolated_preview_origin()
    editor = urlsplit(workbench_url)
    editor_origin = f"{editor.scheme}://{editor.netloc}"
    nonce = uuid4().hex

    def js(value: str) -> str:
        """安全序列化脚本字符串，避免 HTML 解析器识别闭合 script 标签。"""
        return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")

    html = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<style nonce="{nonce}">html,body,iframe{{margin:0;border:0;width:100%;height:100%;overflow:hidden}}iframe{{display:block}}#back{{position:fixed;right:16px;top:16px;padding:8px 12px;background:white;color:#0f172a;border:1px solid #cbd5e1;border-radius:6px;font:14px system-ui;text-decoration:none}}</style>
</head><body><iframe id="preview" src="{escape(target, quote=True)}" title="内容预览" referrerpolicy="origin" allow="clipboard-write; autoplay; fullscreen"></iframe><a id="back" href="{escape(workbench_url, quote=True)}" target="_top" hidden>返回工作台重新授权</a>
<script nonce="{nonce}">
const frame=document.getElementById('preview');
const runtimeOrigin={js(target_origin)}, editorOrigin={js(editor_origin)};
window.addEventListener('message', event=>{{
  if (!event.data || typeof event.data !== 'object') return;
  if (event.source === frame.contentWindow && event.origin === runtimeOrigin) {{
    if (window.parent === window && String(event.data.type || '').endsWith(':error')) document.getElementById('back').hidden=false;
    if (window.parent !== window) window.parent.postMessage(event.data,editorOrigin);
  }} else if (window.parent !== window && event.source === window.parent && event.origin === editorOrigin) {{
    frame.contentWindow.postMessage(event.data,runtimeOrigin);
  }}
}});
</script></body></html>'''
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            f"frame-src {target_origin}; base-uri 'none'; form-action 'none'"
        ),
    })
