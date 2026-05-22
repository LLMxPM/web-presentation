"""文件功能：向 Runtime 提供内部 preview artifact 读取与构建产物上传接口。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.models.project_build_job import ProjectBuildJob
from app.models.release import Release, ReleaseModule
from app.services.project_build_service import ProjectBuildService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService

router = APIRouter()


async def _get_release_or_404(session: AsyncSession, artifact_id: str) -> Release:
    """按 artifact_id 读取 release 记录，不存在时返回标准 404。"""

    try:
        release_id = int(str(artifact_id))
    except ValueError as exc:
        raise HTTPException(404, "ARTIFACT_NOT_FOUND") from exc
    stmt = select(Release).where(Release.id == release_id)
    release = (await session.execute(stmt)).scalar_one_or_none()
    if release is None:
        raise HTTPException(404, "ARTIFACT_NOT_FOUND")
    return release


async def _get_build_job_or_404(session: AsyncSession, job_id: int) -> ProjectBuildJob:
    """按构建任务 ID 读取任务记录，不存在时返回标准 404。"""

    stmt = select(ProjectBuildJob).where(ProjectBuildJob.id == job_id)
    build_job = (await session.execute(stmt)).scalar_one_or_none()
    if build_job is None:
        raise HTTPException(404, "BUILD_JOB_NOT_FOUND")
    return build_job


def _read_bearer_token(
    request: Request,
    *,
    missing_code: str = "BUILD_TOKEN_REQUIRED",
    missing_detail: str = "缺少 Bearer 构建令牌。",
) -> str:
    """从 Authorization 头中提取 Bearer Token。"""

    authorization = str(request.headers.get("authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        raise AppException(status_code=401, code=missing_code, detail=missing_detail)
    return authorization[len("Bearer "):].strip()


def _verify_runtime_service_request(request: Request, artifact_id: str) -> dict[str, object]:
    """校验 Runtime 调用 Backend 内部 preview artifact 接口时的服务级令牌。"""

    service_token = _read_bearer_token(
        request,
        missing_code="RUNTIME_SERVICE_TOKEN_REQUIRED",
        missing_detail="缺少 Runtime 服务级 Bearer 令牌。",
    )
    try:
        claims = TokenService.verify_runtime_service_access_token(service_token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(
            status_code=401,
            code="RUNTIME_SERVICE_TOKEN_INVALID",
            detail="Runtime 服务令牌非法、artifact 不匹配或已过期。",
        ) from exc
    token_artifact_id = str(claims.get("artifact_id") or "").strip()
    if token_artifact_id and token_artifact_id != str(artifact_id):
        raise AppException(status_code=403, code="PREVIEW_ARTIFACT_MISMATCH", detail="服务令牌与目标 artifact 不一致。")
    return claims


def _verify_optional_preview_context(request: Request, artifact_id: str) -> None:
    """若请求附带 PreviewContextToken，则额外校验其 artifact 归属。"""

    preview_token = str(request.headers.get("x-runtime-preview-context") or "").strip()
    if not preview_token:
        return

    try:
        claims = TokenService.verify_preview_context_token(preview_token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(status_code=401, code="PREVIEW_CONTEXT_INVALID", detail="预览上下文令牌非法或已过期。") from exc

    if str(claims.get("artifact_id") or "") != str(artifact_id):
        raise AppException(status_code=403, code="PREVIEW_ARTIFACT_MISMATCH", detail="预览上下文与目标 artifact 不一致。")


@router.get("/internal/runtime/preview-artifacts/{artifact_id}/manifest")
async def get_preview_artifact_manifest(
    artifact_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """返回给定 preview artifact 的清单，含入口描述、白名单模块和资源映射。"""

    _verify_runtime_service_request(request, artifact_id)
    _verify_optional_preview_context(request, artifact_id)
    runtime_manifest = await RuntimeArtifactStore().get_manifest(artifact_id)
    if runtime_manifest is not None:
        return runtime_manifest
    release = await _get_release_or_404(session, artifact_id)
    manifest = dict(release.manifest or {})
    manifest["artifact_id"] = str(release.id)
    manifest["version"] = release.version or ""
    return manifest


@router.get("/internal/runtime/preview-artifacts/{artifact_id}/config-bundle")
async def get_preview_artifact_config_bundle(
    artifact_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """返回 preview artifact 的 JSON 配置包。"""

    _verify_runtime_service_request(request, artifact_id)
    _verify_optional_preview_context(request, artifact_id)
    runtime_config_bundle = await RuntimeArtifactStore().get_config_bundle(artifact_id)
    if runtime_config_bundle is not None:
        return runtime_config_bundle
    release = await _get_release_or_404(session, artifact_id)
    return release.config_bundle


@router.get("/internal/runtime/preview-artifacts/{artifact_id}/modules")
async def get_preview_artifact_module(
    artifact_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    path: str = Query(...),
):
    """返回 preview artifact 下指定逻辑模块的源码文本。"""

    _verify_runtime_service_request(request, artifact_id)
    _verify_optional_preview_context(request, artifact_id)
    runtime_module = await RuntimeArtifactStore().get_module(artifact_id, path)
    if runtime_module is not None:
        return Response(content=runtime_module, media_type="text/plain")
    try:
        release_id = int(str(artifact_id))
    except ValueError as exc:
        raise HTTPException(404, "MODULE_NOT_FOUND") from exc
    stmt = select(ReleaseModule).where(
        ReleaseModule.release_id == release_id,
        ReleaseModule.logical_path == path,
    )
    module = (await session.execute(stmt)).scalar_one_or_none()
    if module is None:
        raise HTTPException(404, "MODULE_NOT_FOUND")

    return Response(content=module.content, media_type="text/plain")


@router.post("/internal/runtime/build-jobs/{job_id}/artifact")
async def upload_project_build_artifact(
    job_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    archive: UploadFile = File(...),
    entry_file: str = Form(...),
    sha256: str | None = Form(default=None),
    size_bytes: int | None = Form(default=None),
):
    """接收 Runtime 上传的构建归档，并写回任务元数据。"""

    build_token = _read_bearer_token(request)
    try:
        claims = TokenService.verify_runtime_build_command_token(build_token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(status_code=401, code="BUILD_TOKEN_INVALID", detail="构建令牌非法或已过期。") from exc
    build_job = await _get_build_job_or_404(session, job_id)
    if str(claims.get("job_id") or "") != str(build_job.id):
        raise AppException(status_code=403, code="BUILD_JOB_MISMATCH", detail="构建任务与令牌声明不一致。")
    if str(claims.get("artifact_id") or "") != str(build_job.snapshot_release_id):
        raise AppException(status_code=403, code="BUILD_ARTIFACT_MISMATCH", detail="构建快照与令牌声明不一致。")
    if str(claims.get("project_id") or "") != str(build_job.project_id):
        raise AppException(status_code=403, code="BUILD_PROJECT_MISMATCH", detail="项目与令牌声明不一致。")

    await RuntimeArtifactStore().put_build_state(
        job_id=build_job.id,
        mapping={
            "status": "uploading",
            "snapshot_release_id": build_job.snapshot_release_id,
            "project_id": build_job.project_id,
            "base_url": build_job.base_url,
            "last_heartbeat_at": datetime.now().astimezone().isoformat(),
            "error_message": "",
        },
    )
    archive_content = await archive.read()
    service = ProjectBuildService(session)
    build_job = await service.persist_uploaded_artifact(
        job=build_job,
        archive_content=archive_content,
        entry_file=entry_file,
        sha256=sha256,
        size_bytes=size_bytes,
    )
    await session.commit()

    return {
        "job_id": build_job.id,
        "artifact_storage_key": build_job.artifact_storage_key,
        "artifact_download_url": build_job.artifact_download_url,
        "artifact_proxy_url": build_job.artifact_proxy_url,
        "artifact_entry_file": build_job.artifact_entry_file,
        "artifact_sha256": build_job.artifact_sha256,
        "artifact_size_bytes": build_job.artifact_size_bytes,
        "message": "构建产物上传完成。",
    }
