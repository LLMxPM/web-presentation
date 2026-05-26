"""文件功能：提供预览 artifact 创建接口，并实现 Browser -> Runtime 的无状态预览代理。"""

from __future__ import annotations

import time
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging_config import get_current_request_id
from app.db.session import get_db_session
from app.schemas.release import PreviewArtifactCreateRequest, PreviewArtifactResponse
from app.services.auth_service import AuthContext
from app.services.preview_service import PreviewService
from app.services.project_service import ProjectService
from app.services.token_service import TokenService

router_admin = APIRouter()
router_public = APIRouter()
RUNTIME_SERVICE_TOKEN_HEADER = "x-runtime-service-token"
logger = logging.getLogger(__name__)


@router_admin.post("/{project_id}/preview-artifacts", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_preview_artifact(
    project_id: int,
    payload: PreviewArtifactCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """基于项目当前状态创建无状态预览 artifact。"""

    await ProjectService(session).get(project_id, user_id=current.user.id)
    tenant_id = f"tenant_{current.user.id}"
    return await PreviewService(session).create_preview_artifact(
        project_id=project_id,
        entry_descriptor=payload.entry_descriptor,
        tenant_id=tenant_id,
    )


@router_public.get("/preview/artifacts/{artifact_id}", summary="代理给 Runtime 执行预览展示")
async def preview_artifact_proxy(
    artifact_id: str,
    request: Request,
    token: str,
):
    """对外代理预览入口，并把签名上下文透传给 Runtime。"""

    try:
        preview_claims = TokenService.verify_preview_context_token(token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(status_code=401, code="PREVIEW_CONTEXT_INVALID", detail="预览上下文令牌非法或已过期。") from exc
    if str(preview_claims.get("artifact_id") or "") != str(artifact_id):
        raise HTTPException(status_code=403, detail="PREVIEW_ARTIFACT_MISMATCH")
    service_token_ttl_seconds = _resolve_runtime_service_token_ttl(preview_claims)
    runtime_service_token = TokenService.generate_runtime_service_access_token(
        artifact_id=str(artifact_id),
        expires_in_seconds=service_token_ttl_seconds,
    )
    return await _proxy_runtime_preview(request, token, runtime_service_token)


async def _proxy_runtime_preview(request: Request, preview_token: str, runtime_service_token: str) -> StreamingResponse:
    """统一代理 Runtime `/__preview`，并透传预览上下文 Token。"""

    settings = get_settings()
    runtime_url = f"{settings.runtime_base_url.rstrip('/')}/__preview"
    runtime_public_base_url = str(settings.runtime_public_base_url or settings.runtime_base_url).strip().rstrip("/")

    headers = dict(request.headers)
    headers.pop("host", None)
    headers["x-runtime-preview-context"] = preview_token
    headers["x-runtime-public-base-url"] = runtime_public_base_url
    headers[RUNTIME_SERVICE_TOKEN_HEADER] = runtime_service_token
    headers["X-Request-ID"] = get_current_request_id()

    try:
        async with httpx.AsyncClient(timeout=settings.runtime_request_timeout_seconds) as client:
            response = await client.get(runtime_url, headers=headers)
    except httpx.TimeoutException as exc:
        logger.error("Runtime 预览入口请求超时。", extra={"event": "runtime.preview.timeout"})
        raise AppException(status_code=504, code="RUNTIME_PREVIEW_TIMEOUT", detail="Runtime 预览入口请求超时。") from exc
    except httpx.RequestError as exc:
        logger.error("Runtime 预览入口不可访问。", extra={"event": "runtime.preview.unavailable"})
        raise AppException(status_code=502, code="RUNTIME_PREVIEW_UNAVAILABLE", detail="Runtime 预览入口不可访问。") from exc
    logger.info(
        "Runtime 预览入口代理完成。",
        extra={"event": "runtime.preview.proxy.completed", "status_code": response.status_code},
    )

    return StreamingResponse(
        iter([response.content]),
        status_code=response.status_code,
        headers={"Content-Type": response.headers.get("Content-Type", "text/html")},
    )


def _resolve_runtime_service_token_ttl(preview_claims: dict[str, object]) -> int:
    """按预览上下文令牌的剩余有效期生成 Runtime 服务令牌 TTL。"""

    now = int(time.time())
    preview_exp = int(preview_claims.get("exp") or now)
    return max(60, preview_exp - now)
