"""文件功能：创建项目整包构建任务、生成构建快照，并以持久领取与 attempt 围栏调度 Runtime 执行构建。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import hashlib
import logging
from pathlib import Path
import re
import uuid

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.models.workspace import Project
from app.models.release import Release, ReleaseModule
from app.schemas.project_build import ProjectBuildAssetSummary, ProjectBuildCreateRequest
from app.services.project_artifact_builder import ProjectArtifactBuilder
from app.services.object_storage_service import ObjectStorageService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_build_client import RuntimeBuildClient
from app.services.token_service import TokenService


ACTIVE_BUILD_STATUSES = ("pending", "running")
logger = logging.getLogger(__name__)


class ProjectBuildService:
    """项目整包构建服务。"""

    def __init__(self, session: AsyncSession, *, lease_owner: str | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.artifact_builder = ProjectArtifactBuilder(session)
        self.object_storage = ObjectStorageService()
        # 执行者身份：同一进程内多次领取使用同一 owner，便于租约续期与结果围栏对齐。
        self.lease_owner = lease_owner or f"build-worker:{uuid.uuid4().hex}"

    async def create_build_job(
        self,
        *,
        project_id: int,
        payload: ProjectBuildCreateRequest,
        created_by: int | None,
        commit: bool = True,
    ) -> ProjectBuildJob:
        """创建整项目构建任务，并写入不可变构建快照。"""

        project_lock = await self.session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        if project_lock is None:
            await self.artifact_builder.get_project_or_raise(project_id)

        active_job = await self.get_active_job(project_id)
        if active_job is not None:
            raise AppException(
                status_code=409,
                code="PROJECT_BUILD_ALREADY_RUNNING",
                detail="当前项目已有构建任务正在执行，请等待完成后再发起构建。",
                data={
                    "active_job_id": active_job.id,
                    "active_job_status": active_job.status,
                },
            )

        normalized_base_url = normalize_project_build_base_url(payload.base_url)
        snapshot = await self.artifact_builder.build_snapshot(
            project_id=project_id,
            asset_delivery_mode="backend_cache",
            asset_snapshot_mode="referenced",
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

        now = utc_now()
        job = ProjectBuildJob(
            project_id=project_id,
            snapshot_release_id=release.id,
            base_url=normalized_base_url,
            status="pending",
            created_by=created_by,
            # 创建即分配初始 attempt 身份，产物上传从一开始就绑定不可变对象键。
            attempt_id=uuid.uuid4().hex,
            attempt_count=0,
            max_attempts=self.settings.project_build_max_attempts,
            deadline_at=now + timedelta(seconds=self.settings.project_build_total_deadline_seconds),
        )
        self.session.add(job)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
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
                "last_heartbeat_at": utc_now().isoformat(),
                "error_message": "",
            },
        )
        logger.info(
            "项目构建任务已创建。",
            extra={
                "event": "project.build.job.created",
                "job_id": job.id,
                "project_id": project_id,
                "workspace_id": snapshot.project.workspace_id,
                "artifact_id": str(release.id),
                "base_url": job.base_url,
            },
        )
        return job

    async def get_asset_summary(self, project_id: int) -> ProjectBuildAssetSummary:
        """读取项目当前构建资源引用摘要。"""

        summary = await self.artifact_builder.collect_project_build_asset_reference_summary(project_id)
        return ProjectBuildAssetSummary(
            automatic_asset_names=summary.automatic_asset_names,
            extra_asset_names=summary.extra_asset_names,
            included_asset_names=summary.included_asset_names,
            dynamic_module_paths=summary.dynamic_module_paths,
        )

    async def get_active_job(self, project_id: int) -> ProjectBuildJob | None:
        """读取项目当前仍在执行链路中的构建任务。"""

        await self.artifact_builder.get_project_or_raise(project_id)
        stmt = (
            select(ProjectBuildJob)
            .where(
                ProjectBuildJob.project_id == project_id,
                ProjectBuildJob.status.in_(ACTIVE_BUILD_STATUSES),
            )
            .order_by(ProjectBuildJob.created_at.desc(), ProjectBuildJob.id.desc())
        )
        return (await self.session.execute(stmt)).scalars().first()

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

    # ------------------ 持久领取、租约与 attempt 围栏 ------------------

    async def claim_job(
        self,
        *,
        job_id: int | None = None,
        lease_owner: str | None = None,
    ) -> ProjectBuildJob | None:
        """有条件领取构建任务：仅 pending 且未持有有效租约时可被认领。

        使用条件 UPDATE（CAS）保证 SQLite 单领取者与 PostgreSQL 多协调者竞争下
        同一任务最多被一个执行者取得；成功后写入新的 attempt_id、租约截止与重试计数。
        """

        owner = lease_owner or self.lease_owner
        now = utc_now()
        lease_seconds = self.settings.project_build_lease_seconds
        expires_at = now + timedelta(seconds=lease_seconds)
        new_attempt_id = uuid.uuid4().hex

        candidate_stmt = select(ProjectBuildJob.id).where(
            ProjectBuildJob.status == "pending",
            or_(
                ProjectBuildJob.lease_expires_at.is_(None),
                ProjectBuildJob.lease_expires_at <= now,
            ),
        )
        if job_id is not None:
            candidate_stmt = candidate_stmt.where(ProjectBuildJob.id == job_id)
        else:
            candidate_stmt = candidate_stmt.order_by(
                ProjectBuildJob.created_at.asc(),
                ProjectBuildJob.id.asc(),
            )
        candidate_ids = list((await self.session.execute(candidate_stmt.limit(10))).scalars().all())
        # 候选读取不应维持 SQLite 读事务，避免并发认领升级写锁失败。
        await self.session.commit()

        for candidate_id in candidate_ids:
            result = await self.session.execute(
                update(ProjectBuildJob)
                .where(
                    ProjectBuildJob.id == candidate_id,
                    ProjectBuildJob.status == "pending",
                    or_(
                        ProjectBuildJob.lease_expires_at.is_(None),
                        ProjectBuildJob.lease_expires_at <= now,
                    ),
                )
                .values(
                    status="running",
                    lease_owner=owner,
                    lease_expires_at=expires_at,
                    claimed_at=now,
                    attempt_id=new_attempt_id,
                    attempt_count=ProjectBuildJob.attempt_count + 1,
                    error_message=None,
                    started_at=now,
                    finished_at=None,
                )
                .execution_options(synchronize_session=False)
            )
            if (result.rowcount or 0) == 1:
                await self.session.commit()
                claimed = await self.session.get(ProjectBuildJob, candidate_id)
                if claimed is not None:
                    await self.session.refresh(claimed)
                return claimed
        return None

    async def release_job_to_pending(
        self,
        *,
        job_id: int,
        lease_owner: str,
        error_message: str | None = None,
    ) -> bool:
        """失败但仍有重试预算时回到 pending；作废当前 attempt，阻止迟到上传提升。"""

        result = await self.session.execute(
            update(ProjectBuildJob)
            .where(
                ProjectBuildJob.id == job_id,
                ProjectBuildJob.status == "running",
                ProjectBuildJob.lease_owner == lease_owner,
            )
            .values(
                status="pending",
                lease_owner=None,
                lease_expires_at=None,
                claimed_at=None,
                # 作废 attempt 身份：旧令牌不得再把迟到产物提升为最终结果。
                attempt_id=None,
                error_message=error_message,
                finished_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return (result.rowcount or 0) == 1

    async def complete_job(
        self,
        *,
        job_id: int,
        lease_owner: str,
        success: bool,
        error_message: str | None = None,
    ) -> bool:
        """在仍持有任务租约时写入终态，避免迟到执行者覆盖新结果。"""

        now = utc_now()
        values: dict[str, object] = {
            "status": "succeeded" if success else "failed",
            "error_message": None if success else error_message,
            "finished_at": now,
        }
        if success:
            values["lease_expires_at"] = None
        result = await self.session.execute(
            update(ProjectBuildJob)
            .where(
                ProjectBuildJob.id == job_id,
                ProjectBuildJob.status == "running",
                ProjectBuildJob.lease_owner == lease_owner,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return (result.rowcount or 0) == 1

    def is_retry_allowed(self, job: ProjectBuildJob) -> bool:
        """判断失败后是否仍可重试：未超重试预算且未超过总 deadline。"""

        now = utc_now()
        if job.deadline_at is not None and now >= job.deadline_at:
            return False
        attempt_limit = job.max_attempts or self.settings.project_build_max_attempts
        return int(job.attempt_count or 0) < int(attempt_limit)

    def build_attempt_storage_key(self, job: ProjectBuildJob) -> str:
        """生成按任务与 attempt 隔离的不可变产物对象键。"""

        attempt_part = (job.attempt_id or "unclaimed").strip() or "unclaimed"
        return f"build-artifacts/{job.project_id}/{job.id}/attempts/{attempt_part}/dist.zip"

    def assert_attempt_fence(
        self,
        *,
        job: ProjectBuildJob,
        attempt_id: str | None,
        lease_owner: str | None = None,
    ) -> None:
        """校验上传 attempt 与有效租约均匹配，否则拒绝提升为最终产物。"""

        if job.status not in ("pending", "running"):
            raise AppException(
                status_code=409,
                code="BUILD_JOB_NOT_EXECUTABLE",
                detail="构建任务已结束，迟到上传不得覆盖已有结果。",
                data={"job_id": job.id, "status": job.status},
            )
        normalized_attempt = str(attempt_id or "").strip()
        job_attempt = str(job.attempt_id or "").strip()
        if not normalized_attempt or normalized_attempt != job_attempt:
            raise AppException(
                status_code=409,
                code="BUILD_ATTEMPT_MISMATCH",
                detail="构建产物 attempt 与当前任务不一致，迟到上传不得覆盖新结果。",
                data={"job_id": job.id, "attempt_id": job_attempt or None},
            )
        if job.lease_owner:
            if lease_owner and str(lease_owner) != str(job.lease_owner):
                raise AppException(
                    status_code=409,
                    code="BUILD_LEASE_OWNER_MISMATCH",
                    detail="构建产物上传者与当前租约持有者不一致。",
                    data={"job_id": job.id},
                )
            if job.lease_expires_at is not None and job.lease_expires_at <= utc_now():
                raise AppException(
                    status_code=409,
                    code="BUILD_LEASE_EXPIRED",
                    detail="构建任务租约已过期，产物不得提升为最终结果。",
                    data={"job_id": job.id},
                )

    async def delete_artifact(self, *, project_id: int, job_id: int) -> ProjectBuildJob:
        """删除已完成任务的归档文件并清空产物元数据，保留构建历史记录。"""

        job = await self.get_job_by_project_and_id(project_id, job_id)
        if job.status in ACTIVE_BUILD_STATUSES:
            raise AppException(
                status_code=409,
                code="BUILD_ARTIFACT_DELETE_CONFLICT",
                detail="构建任务仍在执行，暂时不能删除产物。",
            )
        if not job.artifact_storage_key:
            raise AppException(
                status_code=404,
                code="BUILD_ARTIFACT_NOT_FOUND",
                detail="当前构建任务没有可删除的产物。",
            )

        await self.object_storage.delete_object(job.artifact_storage_key)
        job.artifact_storage_key = None
        job.artifact_download_url = None
        job.artifact_entry_file = None
        job.artifact_sha256 = None
        job.artifact_size_bytes = None
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def persist_uploaded_artifact(
        self,
        *,
        job: ProjectBuildJob,
        archive_content: bytes,
        entry_file: str,
        sha256: str | None,
        size_bytes: int | None,
        attempt_id: str | None = None,
        lease_owner: str | None = None,
    ) -> ProjectBuildJob:
        """保存 Runtime 上传的构建归档；仅在 attempt 与有效租约匹配时提升为最终产物。"""

        if not archive_content:
            raise AppException(status_code=400, code="BUILD_ARTIFACT_EMPTY", detail="构建产物归档不能为空。")

        self.assert_attempt_fence(job=job, attempt_id=attempt_id, lease_owner=lease_owner)

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

        # 先写入 attempt 级不可变对象键，再提升任务上的最终产物指针。
        storage_key = self.build_attempt_storage_key(job)
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
                "last_heartbeat_at": utc_now().isoformat(),
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


async def run_project_build_job(
    job_id: int,
    *,
    lease_owner: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """领取并执行整项目构建任务；失败时按重试预算回到 pending 或标为 failed。"""

    factory = session_factory or get_session_factory()
    owner = lease_owner or f"build-worker:{uuid.uuid4().hex}"
    async with factory() as session:
        service = ProjectBuildService(session, lease_owner=owner)
        job = await service.claim_job(job_id=job_id, lease_owner=owner)
        if job is None:
            # 已被其他执行者领取或不可领取，不重复派发。
            return

        # 回滚后 ORM 实例会过期，提前固化关键标识。
        claimed_job_id = job.id
        claimed_project_id = job.project_id
        claimed_snapshot_release_id = job.snapshot_release_id
        claimed_base_url = job.base_url

        await RuntimeArtifactStore().put_build_state(
            job_id=claimed_job_id,
            mapping={
                "status": "running",
                "snapshot_release_id": claimed_snapshot_release_id,
                "project_id": claimed_project_id,
                "base_url": claimed_base_url,
                "runtime_dispatch_at": "",
                "last_heartbeat_at": utc_now().isoformat(),
                "error_message": "",
            },
        )
        logger.info(
            "项目构建任务开始执行。",
            extra={
                "event": "project.build.job.started",
                "job_id": claimed_job_id,
                "project_id": claimed_project_id,
                "attempt_id": job.attempt_id,
                "attempt_count": job.attempt_count,
                "lease_owner": owner,
            },
        )

        try:
            release = await session.get(Release, claimed_snapshot_release_id)
            if release is None:
                raise AppException(status_code=404, code="BUILD_SNAPSHOT_NOT_FOUND", detail="构建快照不存在。")

            owner_scope = dict(release.manifest.get("owner_scope") or {})
            project_id = int(owner_scope.get("project_id") or claimed_project_id)
            workspace_id = int(owner_scope.get("workspace_id") or 0)
            if workspace_id <= 0:
                raise AppException(status_code=409, code="BUILD_SCOPE_INVALID", detail="构建快照缺少工作空间归属。")

            build_token = TokenService.generate_runtime_build_command_token(
                job_id=claimed_job_id,
                artifact_id=str(claimed_snapshot_release_id),
                project_id=project_id,
                workspace_id=workspace_id,
                base_url=claimed_base_url,
                attempt_id=job.attempt_id,
                lease_owner=owner,
            )
            await RuntimeArtifactStore().put_build_state(
                job_id=claimed_job_id,
                mapping={
                    "status": "runtime_dispatched",
                    "snapshot_release_id": claimed_snapshot_release_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "base_url": claimed_base_url,
                    "runtime_dispatch_at": utc_now().isoformat(),
                    "last_heartbeat_at": utc_now().isoformat(),
                    "error_message": "",
                },
            )
            logger.info(
                "项目构建任务已派发 Runtime。",
                extra={
                    "event": "project.build.job.dispatched",
                    "job_id": claimed_job_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "artifact_id": str(claimed_snapshot_release_id),
                    "attempt_id": job.attempt_id,
                },
            )
            await RuntimeBuildClient().dispatch_project_build(
                artifact_id=str(claimed_snapshot_release_id),
                base_url=claimed_base_url,
                build_token=build_token,
            )
            completed = await service.complete_job(
                job_id=claimed_job_id,
                lease_owner=owner,
                success=True,
            )
            if not completed:
                logger.warning(
                    "项目构建成功但租约已失守，结果不由本执行者提交。",
                    extra={"event": "project.build.job.success_lost_lease", "job_id": claimed_job_id},
                )
                return
            await RuntimeArtifactStore().put_build_state(
                job_id=claimed_job_id,
                mapping={
                    "status": "succeeded",
                    "snapshot_release_id": claimed_snapshot_release_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "base_url": claimed_base_url,
                    "last_heartbeat_at": utc_now().isoformat(),
                    "error_message": "",
                },
            )
            logger.info(
                "项目构建任务执行成功。",
                extra={"event": "project.build.job.succeeded", "job_id": claimed_job_id, "project_id": project_id},
            )
        except Exception as exc:  # noqa: BLE001
            error_message = _extract_build_error_message(exc)
            # 先刷新任务以读取最新 attempt 预算，再决定重试或终止。
            await session.rollback()
            current = await service.get_job_by_id(claimed_job_id)
            if service.is_retry_allowed(current):
                requeued = await service.release_job_to_pending(
                    job_id=claimed_job_id,
                    lease_owner=owner,
                    error_message=error_message,
                )
                if requeued:
                    await RuntimeArtifactStore().put_build_state(
                        job_id=claimed_job_id,
                        mapping={
                            "status": "pending",
                            "snapshot_release_id": current.snapshot_release_id,
                            "project_id": current.project_id,
                            "base_url": current.base_url,
                            "last_heartbeat_at": utc_now().isoformat(),
                            "error_message": error_message,
                        },
                    )
                    logger.warning(
                        "项目构建任务失败，仍在重试预算内已回到 pending。",
                        extra={
                            "event": "project.build.job.requeued",
                            "job_id": claimed_job_id,
                            "project_id": current.project_id,
                            "attempt_count": current.attempt_count,
                            "error_message": error_message,
                        },
                    )
                    return
            failed = await service.complete_job(
                job_id=claimed_job_id,
                lease_owner=owner,
                success=False,
                error_message=error_message,
            )
            if not failed:
                logger.warning(
                    "项目构建失败但租约已失守，终态不由本执行者写入。",
                    extra={"event": "project.build.job.failed_lost_lease", "job_id": claimed_job_id},
                )
                return
            await RuntimeArtifactStore().put_build_state(
                job_id=claimed_job_id,
                mapping={
                    "status": "failed",
                    "snapshot_release_id": current.snapshot_release_id,
                    "project_id": current.project_id,
                    "base_url": current.base_url,
                    "last_heartbeat_at": utc_now().isoformat(),
                    "error_message": error_message,
                },
            )
            logger.exception(
                "项目构建任务执行失败。",
                extra={
                    "event": "project.build.job.failed",
                    "job_id": claimed_job_id,
                    "project_id": current.project_id,
                    "artifact_id": str(current.snapshot_release_id),
                },
            )


async def run_project_build_queue_loop(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """持续发现并执行待构建任务，作为 BackgroundTasks 之外的持久派发路径。"""

    settings = get_settings()
    factory = session_factory or get_session_factory()
    poll_interval = max(0.1, settings.project_build_queue_poll_interval_seconds)
    concurrency = max(1, settings.project_build_queue_concurrency)
    lease_owner = f"build-queue:{uuid.uuid4().hex}"
    logger.info(
        "项目构建队列后台任务已启动。",
        extra={"event": "project.build.queue.started", "concurrency": concurrency, "lease_owner": lease_owner},
    )
    while True:
        try:
            async with factory() as session:
                # 先收敛租约过期的 running 任务，再发现可领取的 pending 任务。
                await recover_expired_build_jobs(session)
                now = utc_now()
                pending_ids = list(
                    (
                        await session.execute(
                            select(ProjectBuildJob.id)
                            .where(
                                ProjectBuildJob.status == "pending",
                                or_(
                                    ProjectBuildJob.lease_expires_at.is_(None),
                                    ProjectBuildJob.lease_expires_at <= now,
                                ),
                            )
                            .order_by(ProjectBuildJob.created_at.asc(), ProjectBuildJob.id.asc())
                            .limit(concurrency)
                        )
                    )
                    .scalars()
                    .all()
                )
            if not pending_ids:
                await asyncio.sleep(poll_interval)
                continue
            # 由 run_project_build_job 内部完成条件领取，避免双重 claim。
            await asyncio.gather(
                *[
                    run_project_build_job(
                        job_id,
                        lease_owner=lease_owner,
                        session_factory=factory,
                    )
                    for job_id in pending_ids
                ]
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("项目构建队列循环异常。", extra={"event": "project.build.queue.failed"})
            await asyncio.sleep(poll_interval)


async def recover_expired_build_jobs(session: AsyncSession, *, force: bool = False) -> int:
    """收敛租约过期（或启动强制）的 running 任务：未超预算回 pending，超预算标 failed。"""

    now = utc_now()
    expired_clause = (ProjectBuildJob.lease_expires_at.is_(None)) | (ProjectBuildJob.lease_expires_at <= now)
    conditions = [ProjectBuildJob.status == "running"]
    if not force:
        conditions.append(expired_clause)
    candidates = list(
        (
            await session.execute(
                select(
                    ProjectBuildJob.id,
                    ProjectBuildJob.attempt_count,
                    ProjectBuildJob.max_attempts,
                    ProjectBuildJob.deadline_at,
                ).where(*conditions)
            )
        ).all()
    )
    if not candidates:
        await session.commit()
        return 0

    recovered = 0
    for row in candidates:
        attempt_limit = int(row.max_attempts or 3)
        attempt_count = int(row.attempt_count or 0)
        deadline_at: datetime | None = row.deadline_at
        past_deadline = deadline_at is not None and now >= deadline_at
        base_where = [ProjectBuildJob.id == row.id, ProjectBuildJob.status == "running"]
        if not force:
            base_where.append(expired_clause)
        if attempt_count < attempt_limit and not past_deadline:
            result = await session.execute(
                update(ProjectBuildJob)
                .where(*base_where)
                .values(
                    status="pending",
                    lease_owner=None,
                    lease_expires_at=None,
                    claimed_at=None,
                    error_message="构建租约过期或进程中断，已回到待执行队列。",
                    finished_at=None,
                )
                .execution_options(synchronize_session=False)
            )
        else:
            result = await session.execute(
                update(ProjectBuildJob)
                .where(*base_where)
                .values(
                    status="failed",
                    error_message="构建进程中断或超时，且已用尽重试预算。",
                    finished_at=now,
                    lease_expires_at=None,
                )
                .execution_options(synchronize_session=False)
            )
        recovered += int(result.rowcount or 0)
    await session.commit()
    return recovered


async def recover_interrupted_build_jobs_on_startup(session_factory) -> int:
    """应用启动时收敛仍标记 running 的构建任务，按重试预算回 pending 或标 failed。"""

    async with session_factory() as session:
        recovered = await recover_expired_build_jobs(session, force=True)
        if recovered:
            logger.info(
                "启动时已收敛中断的构建任务。",
                extra={"event": "project.build.job.recovered", "recovered_count": recovered},
            )
        return recovered


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
