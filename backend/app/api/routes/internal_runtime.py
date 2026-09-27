"""文件功能：向 Runtime 提供内部 preview artifact 读取、构建任务领取/续租/完成与产物上传接口。"""

from __future__ import annotations

import hmac
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_db_session
from app.models.project_build_job import ProjectBuildJob
from app.models.release import Release, ReleaseModule
from app.services.project_build_service import ProjectBuildService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService

router = APIRouter()

MAX_BATCH_MODULE_PATHS = 128


class RuntimeModuleBatchRequest(BaseModel):
    """Runtime 批量读取 artifact 模块的内部请求。"""

    paths: list[str] = Field(min_length=1, max_length=MAX_BATCH_MODULE_PATHS)

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: list[str]) -> list[str]:
        """规范路径并拒绝空值和重复项，确保响应一一对应。"""

        normalized = [str(item or "").strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("模块路径不能为空。")
        if len(set(normalized)) != len(normalized):
            raise ValueError("模块路径不能重复。")
        return normalized


class PreviewServiceTokenExchangeRequest(BaseModel):
    """Runtime 用 PreviewContextToken 换取短期服务令牌的内部请求。"""

    preview_token: str = Field(min_length=1)


class PreviewServiceTokenExchangeResponse(BaseModel):
    """换票结果：artifact 作用域的短期 Runtime 服务令牌。"""

    service_token: str
    token_type: str = "Bearer"
    expires_in: int
    artifact_id: str
    scope: str = "runtime-artifact-read"


class BuildJobClaimRequest(BaseModel):
    """Runtime Build Worker 领取构建任务的内部请求。"""

    worker_id: str = Field(min_length=1, max_length=128)


class BuildJobClaimResponse(BaseModel):
    """领取结果：任务载荷与本次 attempt 的限权令牌；无任务时 job_id 为空。"""

    job_id: int | None = None
    project_id: int | None = None
    snapshot_release_id: str | None = None
    base_url: str | None = None
    workspace_id: int | None = None
    attempt_id: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    build_token: str | None = None
    service_token: str | None = None
    message: str = "当前没有可领取的构建任务。"


class BuildJobCompleteRequest(BaseModel):
    """Runtime Build Worker 上报构建终态的内部请求。"""

    success: bool
    error_message: str | None = Field(default=None, max_length=2000)


def _resolve_runtime_service_token_ttl(preview_claims: dict[str, object]) -> int:
    """按 PreviewContextToken 剩余有效期生成短期服务令牌 TTL，至少 60 秒。"""

    now = int(time.time())
    try:
        preview_exp = int(preview_claims.get("exp") or now)
    except (TypeError, ValueError):
        preview_exp = now
    return max(60, preview_exp - now)


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
    """校验 Runtime 调用 Backend 内部 preview artifact 接口时的服务级令牌。

    服务令牌必须绑定目标 artifact：缺失 artifact_id 的令牌一律拒绝，
    避免无作用域令牌抵消 artifact 绑定、对任意 artifact 有效。
    """

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
    if not token_artifact_id:
        raise AppException(
            status_code=401,
            code="RUNTIME_SERVICE_TOKEN_INVALID",
            detail="Runtime 服务令牌缺少 artifact 绑定，不得访问 artifact 接口。",
        )
    if token_artifact_id != str(artifact_id):
        raise AppException(status_code=403, code="PREVIEW_ARTIFACT_MISMATCH", detail="服务令牌与目标 artifact 不一致。")
    return claims


def _resolve_build_worker_credential() -> str:
    """解析 Runtime Build Worker 共享凭证：优先 secret 文件，其次环境变量。"""

    settings = get_settings()
    credential_file = str(settings.runtime_build_worker_credential_file or "").strip()
    if credential_file:
        path = Path(credential_file).expanduser()
        if not path.is_file():
            raise AppException(
                status_code=503,
                code="RUNTIME_BUILD_WORKER_CREDENTIAL_MISSING",
                detail="Runtime Build Worker 凭证文件不存在。",
            )
        return path.read_text(encoding="utf-8").strip()
    return str(settings.runtime_build_worker_credential or "").strip()


def _verify_build_worker_credential(request: Request) -> str:
    """校验 Runtime Build Worker 共享服务凭证；未配置时 fail-closed。"""

    credential = _resolve_build_worker_credential()
    if not credential:
        raise AppException(
            status_code=503,
            code="RUNTIME_BUILD_WORKER_CREDENTIAL_MISSING",
            detail="Backend 未配置 RUNTIME_BUILD_WORKER_CREDENTIAL，无法接受构建任务领取。",
        )
    token = _read_bearer_token(
        request,
        missing_code="RUNTIME_BUILD_WORKER_CREDENTIAL_REQUIRED",
        missing_detail="缺少 Runtime Build Worker 服务凭证。",
    )
    # 常量时间比较，避免通过响应时序侧信道猜测共享凭证。
    if not hmac.compare_digest(token.encode("utf-8"), credential.encode("utf-8")):
        raise AppException(
            status_code=401,
            code="RUNTIME_BUILD_WORKER_CREDENTIAL_INVALID",
            detail="Runtime Build Worker 服务凭证无效。",
        )
    return token


def _verify_build_command_token(request: Request, job: ProjectBuildJob) -> dict[str, Any]:
    """校验构建命令令牌与任务、attempt、租约围栏一致。"""

    build_token = _read_bearer_token(request)
    try:
        claims = TokenService.verify_runtime_build_command_token(build_token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(status_code=401, code="BUILD_TOKEN_INVALID", detail="构建令牌非法或已过期。") from exc
    if str(claims.get("job_id") or "") != str(job.id):
        raise AppException(status_code=403, code="BUILD_JOB_MISMATCH", detail="构建任务与令牌声明不一致。")
    if str(claims.get("artifact_id") or "") != str(job.snapshot_release_id):
        raise AppException(status_code=403, code="BUILD_ARTIFACT_MISMATCH", detail="构建快照与令牌声明不一致。")
    token_attempt_id = str(claims.get("attempt_id") or "").strip() or None
    token_lease_owner = str(claims.get("lease_owner") or "").strip() or None
    job_attempt = str(job.attempt_id or "").strip()
    if not token_attempt_id or token_attempt_id != job_attempt:
        raise AppException(status_code=409, code="BUILD_ATTEMPT_MISMATCH", detail="构建令牌 attempt 与当前任务不一致。")
    if token_lease_owner and job.lease_owner and str(token_lease_owner) != str(job.lease_owner):
        raise AppException(status_code=409, code="BUILD_LEASE_OWNER_MISMATCH", detail="构建令牌租约拥有者不一致。")
    return claims


async def _fail_claimed_build_job(
    service: ProjectBuildService,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
) -> None:
    """把已领取但存在不可重试缺陷的任务直接写成 failed，禁止回到 pending 毒丸循环。"""

    completed = await service.complete_job(
        job_id=job_id,
        lease_owner=lease_owner,
        success=False,
        error_message=error_message,
    )
    if not completed:
        # 租约已失守时终态由其它执行者或恢复循环收敛，这里不覆盖。
        return
    await RuntimeArtifactStore().put_build_state(
        job_id=job_id,
        mapping={
            "status": "failed",
            "error_message": error_message,
            "last_heartbeat_at": utc_now().isoformat(),
        },
    )


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


def _allowed_artifact_module_paths(manifest: dict[str, object]) -> set[str]:
    """返回 manifest 模块白名单，并包含受签名入口描述保护的独立页面入口。"""

    allowed_paths = set(dict(manifest.get("modules") or {}).keys())
    entry_descriptor = manifest.get("entry_descriptor")
    if isinstance(entry_descriptor, dict) and entry_descriptor.get("entry_type") == "module":
        entry_path = str(entry_descriptor.get("module_path") or "").strip()
        if entry_path:
            allowed_paths.add(entry_path)
    return allowed_paths


@router.post(
    "/internal/runtime/preview-service-token",
    response_model=PreviewServiceTokenExchangeResponse,
    response_model_exclude_none=True,
)
async def exchange_preview_service_token(payload: PreviewServiceTokenExchangeRequest) -> PreviewServiceTokenExchangeResponse:
    """用已签名的 PreviewContextToken 换取 artifact 作用域的短期 Runtime 服务令牌。

    授权语义：
    - 仅接受 `aud=runtime-preview` 的有效 PreviewContextToken（验签并校验过期），过期或伪造令牌直接 401；
    - 签发的服务令牌为 `sub=runtime-service`、`scope=runtime-artifact-read`，且绑定 `artifact_id`，只能读取该 artifact；
    - TTL 与预览令牌剩余有效期对齐，属于短期票据，可被 Runtime 反复换发；
    - 本端点位于 `/internal/` 前缀，不经公开 Gateway 暴露，只有受信网络内的 Runtime 可访问；
      响应体包含服务令牌原文，仅供 Runtime 进程内使用，禁止转发给浏览器；
    - 日志只记录 artifact_id，不记录任何令牌原文。
    """

    try:
        claims = TokenService.verify_preview_context_token(payload.preview_token)
    except Exception as exc:  # noqa: BLE001
        raise AppException(
            status_code=401,
            code="PREVIEW_CONTEXT_INVALID",
            detail="预览上下文令牌非法或已过期。",
        ) from exc

    artifact_id = str(claims.get("artifact_id") or "").strip()
    if not artifact_id:
        raise AppException(status_code=401, code="PREVIEW_CONTEXT_INVALID", detail="预览上下文缺少 artifact_id。")

    expires_in = _resolve_runtime_service_token_ttl(claims)
    service_token = TokenService.generate_runtime_service_access_token(
        artifact_id=artifact_id,
        expires_in_seconds=expires_in,
    )
    return PreviewServiceTokenExchangeResponse(
        service_token=service_token,
        expires_in=expires_in,
        artifact_id=artifact_id,
    )


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


@router.post("/internal/runtime/preview-artifacts/{artifact_id}/modules/batch")
async def get_preview_artifact_modules_batch(
    artifact_id: str,
    payload: RuntimeModuleBatchRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """在一次内部请求中返回 manifest 白名单内的多份模块源码。"""

    _verify_runtime_service_request(request, artifact_id)
    _verify_optional_preview_context(request, artifact_id)
    store = RuntimeArtifactStore()
    manifest = await store.get_manifest(artifact_id)
    if manifest is not None:
        allowed_paths = _allowed_artifact_module_paths(manifest)
        if any(path not in allowed_paths for path in payload.paths):
            raise AppException(status_code=404, code="MODULE_NOT_FOUND", detail="批量请求包含 artifact 白名单外的模块。")
        modules = await store.get_modules(artifact_id, payload.paths)
        if modules is None:
            raise AppException(status_code=404, code="MODULE_NOT_FOUND", detail="批量请求中的模块不存在。")
        return {"modules": modules}

    release = await _get_release_or_404(session, artifact_id)
    allowed_paths = _allowed_artifact_module_paths(dict(release.manifest or {}))
    if any(path not in allowed_paths for path in payload.paths):
        raise AppException(status_code=404, code="MODULE_NOT_FOUND", detail="批量请求包含 artifact 白名单外的模块。")
    result = await session.scalars(
        select(ReleaseModule).where(
            ReleaseModule.release_id == release.id,
            ReleaseModule.logical_path.in_(payload.paths),
        )
    )
    modules = {item.logical_path: item.content for item in result.all()}
    if len(modules) != len(payload.paths):
        raise AppException(status_code=404, code="MODULE_NOT_FOUND", detail="批量请求中的模块不存在。")
    return {"modules": {path: modules[path] for path in payload.paths}}


@router.post("/internal/runtime/build-jobs/claim", response_model=BuildJobClaimResponse)
async def claim_project_build_job(
    payload: BuildJobClaimRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BuildJobClaimResponse:
    """Runtime Build Worker 原子领取 pending 构建任务；无任务时返回空 job_id。"""

    _verify_build_worker_credential(request)
    service = ProjectBuildService(session, lease_owner=payload.worker_id)
    job = await service.claim_job(lease_owner=payload.worker_id)
    if job is None:
        return BuildJobClaimResponse(message="当前没有可领取的构建任务。")

    release = await session.get(Release, job.snapshot_release_id)
    if release is None:
        # 缺失快照不可重试：直接终态失败，避免 claim→pending 无限毒丸循环。
        await _fail_claimed_build_job(
            service,
            job_id=job.id,
            lease_owner=payload.worker_id,
            error_message="构建快照不存在。",
        )
        return BuildJobClaimResponse(
            job_id=job.id,
            message="构建快照不存在，任务已标记失败。",
        )

    owner_scope = dict(release.manifest.get("owner_scope") or {})
    workspace_id = int(owner_scope.get("workspace_id") or 0)
    if workspace_id <= 0:
        await _fail_claimed_build_job(
            service,
            job_id=job.id,
            lease_owner=payload.worker_id,
            error_message="构建快照缺少工作空间归属。",
        )
        return BuildJobClaimResponse(
            job_id=job.id,
            message="构建快照缺少工作空间归属，任务已标记失败。",
        )

    # attempt 令牌 TTL 必须覆盖整个任务生命周期（含 renew 续租），
    # 否则 renew/upload/complete 会在票过期后集体 401，续租形同虚设。
    settings = get_settings()
    token_ttl_seconds = max(
        int(settings.project_build_total_deadline_seconds or 0),
        int(settings.project_build_lease_seconds or 0),
        900,
    )
    build_token = TokenService.generate_runtime_build_command_token(
        job_id=job.id,
        artifact_id=str(job.snapshot_release_id),
        project_id=job.project_id,
        workspace_id=workspace_id,
        base_url=job.base_url,
        attempt_id=job.attempt_id,
        lease_owner=payload.worker_id,
        expires_in_seconds=token_ttl_seconds,
    )
    service_token = TokenService.generate_runtime_service_access_token(
        artifact_id=str(job.snapshot_release_id),
        expires_in_seconds=token_ttl_seconds,
    )
    lease_expires_at = job.lease_expires_at.isoformat() if job.lease_expires_at else None
    await RuntimeArtifactStore().put_build_state(
        job_id=job.id,
        mapping={
            "status": "running",
            "snapshot_release_id": job.snapshot_release_id,
            "project_id": job.project_id,
            "workspace_id": workspace_id,
            "base_url": job.base_url,
            "runtime_dispatch_at": utc_now().isoformat(),
            "last_heartbeat_at": utc_now().isoformat(),
            "error_message": "",
        },
    )
    return BuildJobClaimResponse(
        job_id=job.id,
        project_id=job.project_id,
        snapshot_release_id=str(job.snapshot_release_id),
        base_url=job.base_url,
        workspace_id=workspace_id,
        attempt_id=job.attempt_id,
        lease_owner=payload.worker_id,
        lease_expires_at=lease_expires_at,
        build_token=build_token,
        service_token=service_token,
        message="构建任务领取成功。",
    )


@router.post("/internal/runtime/build-jobs/{job_id}/renew")
async def renew_project_build_job_lease(
    job_id: int,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Runtime Build Worker 续租当前 attempt；仅未过期租约的拥有者可续。"""

    build_job = await _get_build_job_or_404(session, job_id)
    claims = _verify_build_command_token(request, build_job)
    token_lease_owner = str(claims.get("lease_owner") or "").strip() or None
    if not token_lease_owner:
        raise AppException(status_code=403, code="BUILD_LEASE_OWNER_REQUIRED", detail="构建令牌缺少租约拥有者。")
    service = ProjectBuildService(session)
    renewed = await service.renew_job_lease(job_id=job_id, lease_owner=token_lease_owner)
    if renewed is None:
        raise AppException(status_code=409, code="BUILD_LEASE_RENEW_REJECTED", detail="构建租约已过期或拥有者不匹配。")
    await RuntimeArtifactStore().put_build_state(
        job_id=job_id,
        mapping={
            "status": "running",
            "snapshot_release_id": renewed.snapshot_release_id,
            "project_id": renewed.project_id,
            "base_url": renewed.base_url,
            "last_heartbeat_at": utc_now().isoformat(),
            "error_message": "",
        },
    )
    return {
        "job_id": job_id,
        "lease_expires_at": renewed.lease_expires_at.isoformat() if renewed.lease_expires_at else None,
        "message": "构建租约已续期。",
    }


@router.post("/internal/runtime/build-jobs/{job_id}/complete")
async def complete_project_build_job(
    job_id: int,
    payload: BuildJobCompleteRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, Any]:
    """Runtime Build Worker 上报构建终态；成功必须已有产物（CAS 围栏）。"""

    build_job = await _get_build_job_or_404(session, job_id)
    claims = _verify_build_command_token(request, build_job)
    token_lease_owner = str(claims.get("lease_owner") or "").strip() or None
    if not token_lease_owner:
        raise AppException(status_code=403, code="BUILD_LEASE_OWNER_REQUIRED", detail="构建令牌缺少租约拥有者。")
    service = ProjectBuildService(session)
    if payload.success:
        completed = await service.complete_job(
            job_id=job_id,
            lease_owner=token_lease_owner,
            success=True,
        )
        if not completed:
            raise AppException(status_code=409, code="BUILD_COMPLETE_REJECTED", detail="构建终态被拒绝：租约失守或缺少产物。")
        await RuntimeArtifactStore().put_build_state(
            job_id=job_id,
            mapping={
                "status": "succeeded",
                "snapshot_release_id": build_job.snapshot_release_id,
                "project_id": build_job.project_id,
                "base_url": build_job.base_url,
                "last_heartbeat_at": utc_now().isoformat(),
                "error_message": "",
            },
        )
        return {"job_id": job_id, "status": "succeeded", "message": "构建任务已标记成功。"}

    error_message = (payload.error_message or "Runtime 构建失败。").strip()
    if service.is_retry_allowed(build_job):
        requeued = await service.release_job_to_pending(
            job_id=job_id,
            lease_owner=token_lease_owner,
            error_message=error_message,
        )
        if requeued:
            await RuntimeArtifactStore().put_build_state(
                job_id=job_id,
                mapping={
                    "status": "pending",
                    "snapshot_release_id": build_job.snapshot_release_id,
                    "project_id": build_job.project_id,
                    "base_url": build_job.base_url,
                    "last_heartbeat_at": utc_now().isoformat(),
                    "error_message": error_message,
                },
            )
            return {"job_id": job_id, "status": "pending", "message": "构建失败仍在重试预算内，已回到 pending。"}
    failed = await service.complete_job(
        job_id=job_id,
        lease_owner=token_lease_owner,
        success=False,
        error_message=error_message,
    )
    if not failed:
        raise AppException(status_code=409, code="BUILD_COMPLETE_REJECTED", detail="构建终态被拒绝：租约失守。")
    await RuntimeArtifactStore().put_build_state(
        job_id=job_id,
        mapping={
            "status": "failed",
            "snapshot_release_id": build_job.snapshot_release_id,
            "project_id": build_job.project_id,
            "base_url": build_job.base_url,
            "last_heartbeat_at": utc_now().isoformat(),
            "error_message": error_message,
        },
    )
    return {"job_id": job_id, "status": "failed", "message": "构建任务已标记失败。"}


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

    token_attempt_id = str(claims.get("attempt_id") or "").strip() or None
    token_lease_owner = str(claims.get("lease_owner") or "").strip() or None
    # attempt 与有效租约围栏：迟到上传不得覆盖新 attempt 的结果。
    ProjectBuildService(session).assert_attempt_fence(
        job=build_job,
        attempt_id=token_attempt_id,
        lease_owner=token_lease_owner,
    )

    await RuntimeArtifactStore().put_build_state(
        job_id=build_job.id,
        mapping={
            "status": "uploading",
            "snapshot_release_id": build_job.snapshot_release_id,
            "project_id": build_job.project_id,
            "base_url": build_job.base_url,
            "last_heartbeat_at": utc_now().isoformat(),
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
        attempt_id=token_attempt_id,
        lease_owner=token_lease_owner,
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
