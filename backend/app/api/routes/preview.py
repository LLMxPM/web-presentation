"""文件功能：提供预览 artifact 创建接口，并生成隔离 Runtime 源站的可信宿主页。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.preview_error_response import PreviewDocumentRoute, preview_workbench_url
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.release import (
    PreviewArtifactAccessRenewalResponse,
    PreviewArtifactCreateRequest,
    PreviewArtifactResponse,
)
from app.services.auth_service import AuthContext
from app.services.preview_service import PreviewService
from app.services.preview_version_binding import bind_preview_runtime_version
from app.services.project_service import ProjectService
from app.services.token_service import TokenService

router_admin = APIRouter()
router_access = APIRouter()
router_public = APIRouter(route_class=PreviewDocumentRoute)


@router_access.post(
    "/preview-artifacts/{artifact_id}/access",
    response_model=PreviewArtifactAccessRenewalResponse,
    response_model_exclude_none=True,
    summary="重新检查权限并为当前预览 artifact 续签短期访问票据",
)
async def renew_preview_artifact_access(
    artifact_id: str,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactAccessRenewalResponse:
    """重新检查当前用户权限并为有效 artifact 换发新的短期预览票据 P。"""

    return await PreviewService(session).renew_preview_access(
        artifact_id=artifact_id,
        user_id=current.user.id,
    )


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


@router_public.get("/preview/artifacts/{artifact_id}", summary="返回隔离 Runtime 预览的可信宿主页")
async def preview_artifact_proxy(
    artifact_id: str,
    request: Request,
    token: str,
):
    """校验预览上下文并返回跨主机名 iframe 宿主页，不在业务源站执行用户 HTML。"""

    try:
        preview_claims = TokenService.verify_preview_context_token(token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(status_code=401, code="PREVIEW_CONTEXT_INVALID", detail="预览上下文令牌非法或已过期。") from exc
    if str(preview_claims.get("artifact_id") or "") != str(artifact_id):
        raise HTTPException(status_code=403, detail="PREVIEW_ARTIFACT_MISMATCH")
    bound_preview_token = await bind_preview_runtime_version(preview_claims)
    from app.services.preview_origin_service import preview_shell
    return preview_shell(
        artifact_id=artifact_id, token=bound_preview_token,
        workbench_url=preview_workbench_url(request, preview_claims),
        parameters={k: v for k, v in request.query_params.items() if k != "token"},
    )


@router_public.get(
    "/preview/artifacts/{artifact_id}/assets/{file_hash}",
    summary="受保护的预览素材读取入口",
)
@router_public.head(
    "/preview/artifacts/{artifact_id}/assets/{file_hash}",
    include_in_schema=False,
)
async def get_preview_protected_asset(
    artifact_id: str,
    file_hash: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    download: int = 0,
):
    """受保护的预览素材读取入口，校验预览令牌 P 与快照成员归属，并支持 ETag 与 Range。"""

    from app.services.file_auth_service import FileAuthService
    from app.services.runtime_artifact_store import RuntimeArtifactStore

    manifest = await RuntimeArtifactStore().get_manifest(artifact_id)
    claims = FileAuthService.verify_preview_asset_access(
        request=request,
        artifact_id=artifact_id,
        file_hash=file_hash,
        manifest=manifest,
    )
    return await FileAuthService.serve_protected_artifact_asset(
        request=request,
        artifact_id=artifact_id,
        file_hash=file_hash,
        claims=claims,
        manifest=manifest or {},
        session=session,
        is_download=download == 1,
        is_head=request.method == "HEAD",
    )
