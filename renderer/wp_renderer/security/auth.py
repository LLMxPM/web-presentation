"""文件功能：Renderer 控制进程身份校验，浏览器网络不能访问控制 API。"""

from __future__ import annotations

from fastapi import Header, HTTPException

from render_contracts.tokens import verify_worker_credential


def require_service_token(
    authorization: str | None = Header(default=None),
    x_render_service_token: str | None = Header(default=None),
) -> str:
    """校验 Backend 服务身份 token，成功时返回主体标识。"""

    from wp_renderer.config import get_renderer_settings

    token = x_render_service_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="缺少 Renderer 服务身份凭证。")
    settings = get_renderer_settings()
    subject = verify_worker_credential(token, settings.credential_secret)
    if not subject:
        raise HTTPException(status_code=403, detail="Renderer 服务身份凭证无效。")
    expected_subject = f"backend:{settings.render_worker_id}"
    if subject != expected_subject:
        raise HTTPException(status_code=403, detail="Renderer 服务身份凭证未绑定当前 Worker。")
    return subject
