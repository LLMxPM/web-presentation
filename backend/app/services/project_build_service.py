"""文件功能：创建项目整包构建任务、生成构建快照并调度 Runtime 执行构建。"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.models.release import Release, ReleaseModule
from app.schemas.project_build import ProjectBuildCreateRequest
from app.services.project_artifact_builder import ProjectArtifactBuilder
from app.services.object_storage_service import ObjectStorageService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_build_client import RuntimeBuildClient
from app.services.token_service import TokenService


class ProjectBuildService:
    """项目整包构建服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.artifact_builder = ProjectArtifactBuilder(session)
        self.object_storage = ObjectStorageService()

    async def create_build_job(
        self,
        *,
        project_id: int,
        payload: ProjectBuildCreateRequest,
        created_by: int | None,
    ) -> ProjectBuildJob:
        """创建整项目构建任务，并写入不可变构建快照。"""

        normalized_base_url = normalize_project_build_base_url(payload.base_url)
        snapshot = await self.artifact_builder.build_snapshot(
            project_id=project_id,
            asset_delivery_mode="backend_cache",
        )
        entry_descriptor_payload = snapshot.entry_descriptor.model_dump(mode="python", exclude_none=True)
        tenant_id = f"tenant_{created_by or 'system'}"

        release = Release(
            tenant_id=tenant_id,
            project_id=project_id,
            version="build-snapshot",
            is_draft=True,
            manifest={
                "artifact_kind": "build_snapshot",
                "tenant_id": tenant_id,
                "preview_kind": snapshot.preview_kind,
                "owner_scope": {
                    "scope_type": "project",
                    "project_id": str(project_id),
                    "workspace_id": str(snapshot.project.workspace_id),
                },
                "entry_descriptor": entry_descriptor_payload,
                "asset_base_url": snapshot.asset_base_url,
                "modules": snapshot.modules_metadata,
                "assets": snapshot.asset_mapping,
                "asset_metadata": snapshot.asset_metadata,
            },
            config_bundle=snapshot.config_bundle,
        )
        self.session.add(release)
        await self.session.flush()

        for module_item in snapshot.modules_data:
            self.session.add(
                ReleaseModule(
                    release_id=release.id,
                    logical_path=module_item["logical_path"],
                    content=module_item["content"],
                    content_hash=module_item["content_hash"],
                )
            )

        job = ProjectBuildJob(
            project_id=project_id,
            snapshot_release_id=release.id,
            base_url=normalized_base_url,
            status="pending",
            created_by=created_by,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        await RuntimeArtifactStore().put_build_state(
            job_id=job.id,
            mapping={
                "status": "pending",
                "snapshot_release_id": job.snapshot_release_id,
                "project_id": job.project_id,
                "workspace_id": snapshot.project.workspace_id,
                "base_url": job.base_url,
                "runtime_dispatch_at": "",
                "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                "error_message": "",
            },
        )
        return job

    async def get_latest_job(self, project_id: int) -> ProjectBuildJob | None:
        """读取项目最近一次构建任务。"""

        await self.artifact_builder.get_project_or_raise(project_id)
        stmt = (
            select(ProjectBuildJob)
            .where(ProjectBuildJob.project_id == project_id)
            .order_by(ProjectBuildJob.created_at.desc(), ProjectBuildJob.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_jobs(self, project_id: int, *, limit: int = 20) -> list[ProjectBuildJob]:
        """按时间倒序读取项目构建历史。"""

        await self.artifact_builder.get_project_or_raise(project_id)
        stmt = (
            select(ProjectBuildJob)
            .where(ProjectBuildJob.project_id == project_id)
            .order_by(ProjectBuildJob.created_at.desc(), ProjectBuildJob.id.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_job_by_id(self, job_id: int) -> ProjectBuildJob:
        """按主键读取构建任务。"""

        stmt = select(ProjectBuildJob).where(ProjectBuildJob.id == job_id)
        job = (await self.session.execute(stmt)).scalar_one_or_none()
        if job is None:
            raise AppException(status_code=404, code="BUILD_JOB_NOT_FOUND", detail="构建任务不存在。")
        return job

    async def get_job_by_project_and_id(self, project_id: int, job_id: int) -> ProjectBuildJob:
        """按项目与任务 ID 读取构建任务，避免跨项目越权访问。"""

        stmt = select(ProjectBuildJob).where(
            ProjectBuildJob.id == job_id,
            ProjectBuildJob.project_id == project_id,
        )
        job = (await self.session.execute(stmt)).scalar_one_or_none()
        if job is None:
            raise AppException(status_code=404, code="BUILD_JOB_NOT_FOUND", detail="构建任务不存在。")
        return job

    async def persist_uploaded_artifact(
        self,
        *,
        job: ProjectBuildJob,
        archive_content: bytes,
        entry_file: str,
        sha256: str | None,
        size_bytes: int | None,
    ) -> ProjectBuildJob:
        """保存 Runtime 上传的构建归档，并回写任务元数据。"""

        if not archive_content:
            raise AppException(status_code=400, code="BUILD_ARTIFACT_EMPTY", detail="构建产物归档不能为空。")

        normalized_entry_file = _normalize_build_entry_file(entry_file)
        actual_sha256 = hashlib.sha256(archive_content).hexdigest()
        actual_size_bytes = len(archive_content)
        normalized_declared_sha256 = str(sha256 or "").strip().lower() or None
        if normalized_declared_sha256 and normalized_declared_sha256 != actual_sha256:
            raise AppException(status_code=409, code="BUILD_ARTIFACT_SHA256_MISMATCH", detail="构建产物校验和不匹配。")
        if size_bytes is not None:
            try:
                declared_size_bytes = int(size_bytes)
            except (TypeError, ValueError) as exc:
                raise AppException(status_code=400, code="BUILD_ARTIFACT_SIZE_INVALID", detail="构建产物大小声明非法。") from exc
            if declared_size_bytes != actual_size_bytes:
                raise AppException(status_code=409, code="BUILD_ARTIFACT_SIZE_MISMATCH", detail="构建产物大小声明不匹配。")

        storage_key = f"build-artifacts/{job.project_id}/{job.id}/dist.zip"
        job.artifact_storage_key = await self.object_storage.put_object(
            storage_key,
            archive_content,
            "application/zip",
        )
        job.artifact_download_url = self.build_artifact_download_url(job)
        job.artifact_entry_file = normalized_entry_file
        job.artifact_sha256 = actual_sha256
        job.artifact_size_bytes = actual_size_bytes
        await RuntimeArtifactStore().put_build_state(
            job_id=job.id,
            mapping={
                "status": "upload_completed",
                "snapshot_release_id": job.snapshot_release_id,
                "project_id": job.project_id,
                "base_url": job.base_url,
                "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                "error_message": "",
            },
        )
        await self.session.flush()
        return job

    def build_artifact_download_url(self, job: ProjectBuildJob) -> str:
        """生成管理员下载构建产物的稳定地址。"""

        return (
            f"{self.settings.backend_public_base_url.rstrip('/')}"
            f"/api/projects/{job.project_id}/build-jobs/{job.id}/artifact"
        )


async def run_project_build_job(job_id: int) -> None:
    """后台执行整项目构建任务。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = ProjectBuildService(session)
        job = await service.get_job_by_id(job_id)
        if job.status not in {"pending", "failed"}:
            return

        job.status = "running"
        job.error_message = None
        job.started_at = datetime.now().astimezone()
        job.finished_at = None
        await session.commit()
        await RuntimeArtifactStore().put_build_state(
            job_id=job.id,
            mapping={
                "status": "running",
                "snapshot_release_id": job.snapshot_release_id,
                "project_id": job.project_id,
                "base_url": job.base_url,
                "runtime_dispatch_at": "",
                "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                "error_message": "",
            },
        )

        try:
            release = await session.get(Release, job.snapshot_release_id)
            if release is None:
                raise AppException(status_code=404, code="BUILD_SNAPSHOT_NOT_FOUND", detail="构建快照不存在。")

            owner_scope = dict(release.manifest.get("owner_scope") or {})
            project_id = int(owner_scope.get("project_id") or job.project_id)
            workspace_id = int(owner_scope.get("workspace_id") or 0)
            if workspace_id <= 0:
                raise AppException(status_code=409, code="BUILD_SCOPE_INVALID", detail="构建快照缺少工作空间归属。")

            build_token = TokenService.generate_runtime_build_command_token(
                job_id=job.id,
                artifact_id=str(job.snapshot_release_id),
                project_id=project_id,
                workspace_id=workspace_id,
                base_url=job.base_url,
            )
            await RuntimeArtifactStore().put_build_state(
                job_id=job.id,
                mapping={
                    "status": "runtime_dispatched",
                    "snapshot_release_id": job.snapshot_release_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "base_url": job.base_url,
                    "runtime_dispatch_at": datetime.now().astimezone().isoformat(),
                    "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                    "error_message": "",
                },
            )
            await RuntimeBuildClient().dispatch_project_build(
                artifact_id=str(job.snapshot_release_id),
                base_url=job.base_url,
                build_token=build_token,
            )
            job.status = "succeeded"
            job.error_message = None
            job.finished_at = datetime.now().astimezone()
            await session.commit()
            await RuntimeArtifactStore().put_build_state(
                job_id=job.id,
                mapping={
                    "status": "succeeded",
                    "snapshot_release_id": job.snapshot_release_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "base_url": job.base_url,
                    "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                    "error_message": "",
                },
            )
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error_message = _extract_build_error_message(exc)
            job.finished_at = datetime.now().astimezone()
            await session.commit()
            await RuntimeArtifactStore().put_build_state(
                job_id=job.id,
                mapping={
                    "status": "failed",
                    "snapshot_release_id": job.snapshot_release_id,
                    "project_id": job.project_id,
                    "base_url": job.base_url,
                    "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                    "error_message": job.error_message,
                },
            )


async def recover_interrupted_build_jobs_on_startup(session_factory) -> int:
    """应用启动时收敛仍标记 running 的构建任务。"""

    async with session_factory() as session:
        result = await session.execute(select(ProjectBuildJob).where(ProjectBuildJob.status == "running"))
        jobs = list(result.scalars().all())
        for job in jobs:
            job.status = "failed"
            job.error_message = "构建进程中断或超时。"
            job.finished_at = datetime.now().astimezone()
            await RuntimeArtifactStore().put_build_state(
                job_id=job.id,
                mapping={
                    "status": "failed",
                    "snapshot_release_id": job.snapshot_release_id,
                    "project_id": job.project_id,
                    "base_url": job.base_url,
                    "last_heartbeat_at": datetime.now().astimezone().isoformat(),
                    "error_message": job.error_message,
                },
            )
        if jobs:
            await session.commit()
        return len(jobs)


def normalize_project_build_base_url(raw_base_url: str | None) -> str:
    """规范化整项目构建使用的部署基路径。"""

    normalized = str(raw_base_url or "").strip()
    if not normalized or normalized in {".", "./"}:
        return "./"

    if re.match(r"^https?://", normalized, re.IGNORECASE):
        raise AppException(status_code=400, code="PROJECT_BUILD_BASE_URL_INVALID", detail="base_url 不能是完整 URL。")

    if normalized.startswith("//"):
        raise AppException(status_code=400, code="PROJECT_BUILD_BASE_URL_INVALID", detail="base_url 不能以双斜杠开头。")

    if not normalized.startswith("/"):
        raise AppException(status_code=400, code="PROJECT_BUILD_BASE_URL_INVALID", detail="base_url 仅支持 ./ 或以 / 开头。")

    return normalized if normalized.endswith("/") else f"{normalized}/"


def _extract_build_error_message(error: Exception) -> str:
    """提取构建失败摘要，供任务状态展示。"""

    if isinstance(error, AppException):
        return error.detail
    return str(error) or "构建失败。"


def _normalize_build_entry_file(raw_entry_file: str | None) -> str:
    """规范化构建产物入口文件名，仅允许相对文件路径。"""

    normalized = str(raw_entry_file or "").strip().replace("\\", "/")
    if not normalized:
        raise AppException(status_code=400, code="BUILD_ARTIFACT_ENTRY_FILE_INVALID", detail="构建产物入口文件不能为空。")
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise AppException(status_code=400, code="BUILD_ARTIFACT_ENTRY_FILE_INVALID", detail="构建产物入口文件路径不合法。")
    return normalized
