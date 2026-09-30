"""文件功能：从受信 Runtime 探针绑定预览签名票据的发布版本，不扩大权限或有效期。"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.token_service import TokenService


async def bind_preview_runtime_version(claims: dict[str, Any]) -> str:
    """只对未绑定的已验签票据探测版本；签发子票据保留 artifact/权限/原始 exp。"""

    payload = dict(claims)
    if not payload.get("runtime_version_fingerprint"):
        settings = get_settings()
        url = f"{settings.resolve_runtime_role_base_url('preview')}/__runtime_healthz"
        try:
            async with httpx.AsyncClient(timeout=settings.runtime_request_timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
                identity = response.json()
            kit = str(identity.get("runtime_kit_version") or "").strip()
            build = str(identity.get("build_id") or "").strip()
        except httpx.TimeoutException as exc:
            raise AppException(status_code=504, code="RUNTIME_PREVIEW_TIMEOUT", detail="Runtime 版本探测超时。") from exc
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise AppException(status_code=502, code="RUNTIME_VERSION_UNAVAILABLE", detail="Runtime 版本信息不可用。") from exc
        if not kit or not build:
            raise AppException(status_code=503, code="RUNTIME_VERSION_UNKNOWN", detail="Runtime 未提供发布身份，请升级 Runtime。")
        payload["runtime_version_fingerprint"] = f"{kit}+{build}"
    return TokenService.generate_signed_token(
        payload, expires_in_seconds=max(1, int(payload["exp"]) - int(time.time())),
    )
