"""文件功能：创建项目整包构建任务、生成构建快照，并以持久领取与 attempt 围栏调度 Runtime 执行构建。"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
import uuid
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.engine import Row
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
from app.services.durable_job_lease_service import (
    claim_pending_jobs,
    recover_expired_running_jobs,
    renew_running_job_lease,
    transition_owned_running_job,
)
from app.services.job_runtime_vocabulary import PROJECT_BUILD_VOCABULARY


ACTIVE_BUILD_STATUSES = ("pending", "running")
# 单次领取扫描的候选行数：与 max_claims=1 配合，多扫候选只为提高命中率。
_BUILD_CLAIM_CANDIDATE_LIMIT = 10
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

        认领时序委托 `claim_pending_jobs` + `PROJECT_BUILD_VOCABULARY`；本方法只
        描述构建领域取值（attempt 围栏、deadline 裁剪、产物指针清空）与候选谓词。
        同一任务最多被一个执行者取得的保证来自条件 UPDATE，而不是候选集。
        """

        owner = lease_owner or self.lease_owner
        now = utc_now()
        lease_seconds = self.settings.project_build_lease_seconds
        new_attempt_id = uuid.uuid4().hex

        # 过期任务不得再被领取：与 fail_overdue_pending_build_jobs 对齐，
        # 避免「恢复循环尚未收敛、Worker 已 claim」把超期任务重新拉起。
        deadline_clause = or_(
            ProjectBuildJob.deadline_at.is_(None),
            ProjectBuildJob.deadline_at > now,
        )
        expired_or_absent_lease = or_(
            ProjectBuildJob.lease_expires_at.is_(None),
            ProjectBuildJob.lease_expires_at <= now,
        )
        # 候选列：id 在前，deadline_at 供 claim_values 做租约裁剪。
        candidate_stmt = select(ProjectBuildJob.id, ProjectBuildJob.deadline_at).where(
            ProjectBuildJob.status == "pending",
            deadline_clause,
            expired_or_absent_lease,
        )
        if job_id is not None:
            candidate_stmt = candidate_stmt.where(ProjectBuildJob.id == job_id)
        else:
            candidate_stmt = candidate_stmt.order_by(
                ProjectBuildJob.created_at.asc(),
                ProjectBuildJob.id.asc(),
            )

        def _claim_values(row: Row[Any], claimed_at: datetime, expires_at: datetime) -> dict[str, Any]:
            # 租约本身也受绝对期限约束：剩余预算不足时不得发出越过 deadline 的租约。
            capped = _cap_lease_expiry(expires_at, row[1])
            return {
                "status": "running",
                "lease_owner": owner,
                "lease_expires_at": capped,
                "claimed_at": claimed_at,
                "attempt_id": new_attempt_id,
                "attempt_count": ProjectBuildJob.attempt_count + 1,
                "error_message": None,
                "started_at": claimed_at,
                "finished_at": None,
                # 新 attempt 从干净产物指针开始，避免残留上一轮成功产物。
                **_clear_artifact_fields(),
            }

        def _extra_claim_conditions(row: Row[Any]) -> list[Any]:
            return [deadline_clause, expired_or_absent_lease]

        claimed_ids = await claim_pending_jobs(
            self.session,
            ProjectBuildJob,
            worker_id=owner,
            limit=_BUILD_CLAIM_CANDIDATE_LIMIT,
            lease_seconds=lease_seconds,
            now=now,
            candidate_query=candidate_stmt,
            vocabulary=PROJECT_BUILD_VOCABULARY,
            claim_values=_claim_values,
            extra_claim_conditions=_extra_claim_conditions,
            max_claims=1,
        )
        if not claimed_ids:
            return None
        claimed_id = claimed_ids[0]
        claimed = await self.session.get(ProjectBuildJob, claimed_id)
        if claimed is not None:
            await self.session.refresh(claimed)
        return claimed

    async def renew_job_lease(
        self,
        *,
        job_id: int,
        lease_owner: str,
    ) -> ProjectBuildJob | None:
        """仅允许当前未过期租约的拥有者续租；CAS 语义收编自 durable_job_lease_service。

        新租约以 `deadline_at` 为硬上界：任务超过总期限后不再承认任何所有权，
        续租因此自然收敛为失败，无需调用方另设过期判断。
        """

        job = await self.session.get(ProjectBuildJob, job_id)
        if job is None:
            return None
        renewed = await renew_running_job_lease(
            self.session,
            ProjectBuildJob,
            job_id=job_id,
            worker_id=lease_owner,
            lease_seconds=self.settings.project_build_lease_seconds,
            owner_attr="lease_owner",
            heartbeat_attr="claimed_at",
            not_after=job.deadline_at,
        )
        if not renewed:
            return None
        await self.session.refresh(job)
        return job

    def attempt_token_ttl_seconds(self, job: ProjectBuildJob) -> int:
        """本次 attempt 令牌的 TTL：以任务绝对 deadline 的剩余时间为上限。

        令牌必须覆盖到租约最后一次续租与终态上报，但又不得比任务本身的
        wall-clock 预算更长，否则超期任务仍能凭旧票写结果。
        """

        if job.deadline_at is None:
            return max(
                int(self.settings.project_build_total_deadline_seconds or 0),
                int(self.settings.project_build_lease_seconds or 0),
                900,
            )
        remaining_seconds = (job.deadline_at - utc_now()).total_seconds()
        return max(1, math.ceil(remaining_seconds))

    async def release_job_to_pending(
        self,
        *,
        job_id: int,
        lease_owner: str,
        error_message: str | None = None,
    ) -> bool:
        """失败但仍有重试预算时回到 pending；作废当前 attempt，阻止迟到上传提升。

        必须仍持有有效租约：租约已失守的执行者不得改写任务归属，
        回收由恢复循环按过期租约统一收敛。
        """

        return await transition_owned_running_job(
            self.session,
            ProjectBuildJob,
            job_id=job_id,
            worker_id=lease_owner,
            owner_attr="lease_owner",
            require_active_lease=True,
            values={
                "status": "pending",
                "lease_owner": None,
                "lease_expires_at": None,
                "claimed_at": None,
                # 作废 attempt 身份：旧令牌不得再把迟到产物提升为最终结果。
                "attempt_id": None,
                "error_message": error_message,
                "finished_at": None,
                **_clear_artifact_fields(),
            },
        )

    async def complete_job(
        self,
        *,
        job_id: int,
        lease_owner: str,
        success: bool,
        error_message: str | None = None,
    ) -> bool:
        """在仍持有有效租约时写入终态，避免迟到执行者覆盖新结果。

        成功终态前置校验产物指针：dispatch 返回不等于产物已提升；
        无产物不得标记 succeeded（M10）。成功后一并释放 lease_owner，
        避免行上残留陈旧执行者身份。

        与 renew 保持同一租约口径：租约过期的执行者即使行上仍写着它的
        `lease_owner`，也不得写终态。产物已提升的成功任务由恢复循环按
        `artifact_storage_key` 收敛为 succeeded，不需要过期 Worker 抢写。
        """

        now = utc_now()
        values: dict[str, object] = {
            "status": "succeeded" if success else "failed",
            "error_message": None if success else error_message,
            "finished_at": now,
            # 两种终态都释放执行者身份：任务不再被任何 Worker 持有。
            "lease_owner": None,
            "lease_expires_at": None,
            "claimed_at": None,
        }
        if not success:
            # 失败终态一并作废 attempt 并清理产物指针。
            values["attempt_id"] = None
            values.update(_clear_artifact_fields())

        extra_conditions = []
        if success:
            # 成功必须已有产物：禁止「succeeded 但无产物」的对外可见状态。
            extra_conditions.append(ProjectBuildJob.artifact_storage_key.is_not(None))

        return await transition_owned_running_job(
            self.session,
            ProjectBuildJob,
            job_id=job_id,
            worker_id=lease_owner,
            owner_attr="lease_owner",
            require_active_lease=True,
            values=values,
            extra_conditions=extra_conditions,
        )

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
        # 无租约持有者时不得跳过 owner / 过期检查：回收后的 pending 行若仍带旧 attempt，
        # 此前会同时绕过 owner 与过期两项校验，使死 attempt 仍能提升产物。
        if not job.lease_owner:
            raise AppException(
                status_code=409,
                code="BUILD_LEASE_MISSING",
                detail="构建任务当前没有有效租约，产物不得提升为最终结果。",
                data={"job_id": job.id, "status": job.status},
            )
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
        archive_chunks: AsyncIterator[bytes],
        entry_file: str,
        sha256: str | None,
        size_bytes: int | None,
        attempt_id: str | None = None,
        lease_owner: str | None = None,
    ) -> ProjectBuildJob:
        """流式接收 Runtime 上传的构建归档；仅在 attempt 与有效租约匹配时提升为最终产物。

        归档分片直接写入对象存储，大小与 sha256 在写入过程中算出；超过
        PROJECT_BUILD_ARTIFACT_MAX_BYTES 立即中止，整包不会进入 Backend 进程内存。
        """

        self.assert_attempt_fence(job=job, attempt_id=attempt_id, lease_owner=lease_owner)

        # 提前取出主键：提升失败路径会 rollback，过期后的 ORM 实例在 async 下不能再惰性加载。
        job_id = int(job.id)
        normalized_entry_file = _normalize_build_entry_file(entry_file)
        normalized_declared_sha256 = str(sha256 or "").strip().lower() or None
        declared_size_bytes: int | None = None
        if size_bytes is not None:
            try:
                declared_size_bytes = int(size_bytes)
            except (TypeError, ValueError) as exc:
                raise AppException(status_code=400, code="BUILD_ARTIFACT_SIZE_INVALID", detail="构建产物大小声明非法。") from exc

        # 先写入 attempt 级不可变对象键，再以条件 UPDATE 提升任务上的最终产物指针。
        # 禁止 read-then-write：两个 attempt 交错时后提交者不得凭内存旧值覆盖新结果（M7）。
        storage_key = self.build_attempt_storage_key(job)
        written = await self.object_storage.put_object_stream(
            storage_key,
            archive_chunks,
            "application/zip",
            max_size_bytes=int(self.settings.project_build_artifact_max_bytes),
        )
        stored_key = written.storage_key
        actual_sha256 = written.sha256
        actual_size_bytes = written.size_bytes
        try:
            await self._promote_uploaded_artifact(
                job=job,
                job_id=job_id,
                stored_key=stored_key,
                actual_sha256=actual_sha256,
                actual_size_bytes=actual_size_bytes,
                normalized_entry_file=normalized_entry_file,
                normalized_declared_sha256=normalized_declared_sha256,
                declared_size_bytes=declared_size_bytes,
                attempt_id=attempt_id,
            )
        except BaseException:
            # 校验失败、attempt 围栏失守或提交异常都不得把归档留在对象存储里：
            # 没有任务行引用的对象不会有任何回收路径，只能在这里主动删除。
            await self._discard_unpromoted_artifact(job_id=job_id, storage_key=stored_key)
            raise
        await self.session.refresh(job)
        return job

    async def _promote_uploaded_artifact(
        self,
        *,
        job: ProjectBuildJob,
        job_id: int,
        stored_key: str,
        actual_sha256: str,
        actual_size_bytes: int,
        normalized_entry_file: str,
        normalized_declared_sha256: str | None,
        declared_size_bytes: int | None,
        attempt_id: str | None,
    ) -> None:
        """对拍声明校验和与大小，并在 attempt/租约围栏内把归档提升为最终产物。"""

        if normalized_declared_sha256 and normalized_declared_sha256 != actual_sha256:
            raise AppException(status_code=409, code="BUILD_ARTIFACT_SHA256_MISMATCH", detail="构建产物校验和不匹配。")
        if declared_size_bytes is not None and declared_size_bytes != actual_size_bytes:
            raise AppException(status_code=409, code="BUILD_ARTIFACT_SIZE_MISMATCH", detail="构建产物大小声明不匹配。")

        download_url = self.build_artifact_download_url(job)
        normalized_attempt = str(attempt_id or "").strip()
        promote_conditions = [
            ProjectBuildJob.id == job_id,
            ProjectBuildJob.status.in_(("pending", "running")),
            ProjectBuildJob.attempt_id == normalized_attempt,
            ProjectBuildJob.attempt_id.is_not(None),
        ]
        if job.lease_owner:
            promote_conditions.append(ProjectBuildJob.lease_owner == job.lease_owner)
            if job.lease_expires_at is not None:
                promote_conditions.append(ProjectBuildJob.lease_expires_at > utc_now())

        promote = await self.session.execute(
            update(ProjectBuildJob)
            .where(*promote_conditions)
            .values(
                artifact_storage_key=stored_key,
                artifact_download_url=download_url,
                artifact_entry_file=normalized_entry_file,
                artifact_sha256=actual_sha256,
                artifact_size_bytes=actual_size_bytes,
            )
            .execution_options(synchronize_session=False)
        )
        if (promote.rowcount or 0) != 1:
            await self.session.rollback()
            raise AppException(
                status_code=409,
                code="BUILD_ATTEMPT_MISMATCH",
                detail="构建产物 attempt 与当前任务不一致，迟到上传不得覆盖新结果。",
                data={"job_id": job_id, "attempt_id": normalized_attempt or None},
            )

        job.artifact_storage_key = stored_key
        job.artifact_download_url = download_url
        job.artifact_entry_file = normalized_entry_file
        job.artifact_sha256 = actual_sha256
        job.artifact_size_bytes = actual_size_bytes
        await RuntimeArtifactStore().put_build_state(
            job_id=job_id,
            mapping={
                "status": "upload_completed",
                "snapshot_release_id": job.snapshot_release_id,
                "project_id": job.project_id,
                "base_url": job.base_url,
                "last_heartbeat_at": utc_now().isoformat(),
                "error_message": "",
            },
        )
        await self.session.commit()

    async def _discard_unpromoted_artifact(self, *, job_id: int, storage_key: str) -> None:
        """删除提升失败的 attempt 归档；仍被任务行引用的产物必须保留。

        上传期间租约过期时，恢复循环可能已按 `artifact_storage_key` 把同一 attempt
        收敛为 succeeded，此时对象就是最终产物，删除会让成功任务指向空洞。
        """

        try:
            await self.session.rollback()
            referenced_key = await self.session.scalar(
                select(ProjectBuildJob.artifact_storage_key).where(ProjectBuildJob.id == job_id)
            )
            if referenced_key and str(referenced_key) == storage_key:
                logger.info(
                    "构建产物提升失败但对象仍被任务引用，跳过回收。",
                    extra={
                        "event": "project.build.artifact.discard_skipped",
                        "job_id": job_id,
                        "storage_key": storage_key,
                    },
                )
                return
            await self.object_storage.delete_object(storage_key)
            logger.warning(
                "已回收未提升为最终产物的构建归档。",
                extra={
                    "event": "project.build.artifact.discarded",
                    "job_id": job_id,
                    "storage_key": storage_key,
                },
            )
        except BaseException:
            # 回收失败只降级为日志：不能让清理动作覆盖真正的上传错误，
            # 包括 CancelledError——外层仍会重抛原始异常。
            logger.warning(
                "构建归档回收失败，对象需由存储侧生命周期规则清理。",
                extra={
                    "event": "project.build.artifact.discard_failed",
                    "job_id": job_id,
                    "storage_key": storage_key,
                },
                exc_info=True,
            )

    def build_artifact_download_url(self, job: ProjectBuildJob) -> str:
        """生成管理员下载构建产物的稳定地址。"""

        return (
            f"{self.settings.backend_public_base_url.rstrip('/')}"
            f"/api/projects/{job.project_id}/build-jobs/{job.id}/artifact"
        )


async def run_project_build_queue_loop(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """持续收敛租约过期的构建任务；真正执行由 Runtime Build Worker 通过 claim API 领取。"""

    settings = get_settings()
    factory = session_factory or get_session_factory()
    poll_interval = max(1.0, settings.project_build_queue_poll_interval_seconds)
    logger.info(
        "项目构建恢复循环已启动（不再同步派发，等待 Runtime Build Worker 领取）。",
        extra={"event": "project.build.queue.started", "mode": "recovery-only"},
    )
    while True:
        try:
            async with factory() as session:
                await recover_expired_build_jobs(session)
                await fail_overdue_pending_build_jobs(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("项目构建恢复循环异常。", extra={"event": "project.build.queue.failed"})
        await asyncio.sleep(poll_interval)


def _cap_lease_expiry(expires_at: datetime, deadline_at: datetime | None) -> datetime:
    """把租约截止裁剪到任务绝对 deadline 之前；无 deadline 时原样返回。"""

    if deadline_at is not None and expires_at > deadline_at:
        return deadline_at
    return expires_at


def _clear_artifact_fields() -> dict[str, object]:
    """返回清空产物指针的字段集合，避免跨 attempt 残留旧产物元数据。"""

    return {
        "artifact_storage_key": None,
        "artifact_download_url": None,
        "artifact_entry_file": None,
        "artifact_sha256": None,
        "artifact_size_bytes": None,
    }


async def fail_overdue_pending_build_jobs(session: AsyncSession) -> int:
    """把超过总 deadline 仍停留在 pending 的任务收敛为 failed。

    没有 Runtime Build Worker 领取时任务会一直 pending；超过 deadline 后
    不应再被领取，避免无限悬挂。
    """

    now = utc_now()
    result = await session.execute(
        update(ProjectBuildJob)
        .where(
            ProjectBuildJob.status == "pending",
            ProjectBuildJob.deadline_at.is_not(None),
            ProjectBuildJob.deadline_at <= now,
        )
        .values(
            status="failed",
            error_message="构建任务超过总执行期限仍未被领取。",
            finished_at=now,
            lease_owner=None,
            lease_expires_at=None,
            claimed_at=None,
            attempt_id=None,
            **_clear_artifact_fields(),
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    recovered = int(result.rowcount or 0)
    if recovered:
        logger.warning(
            "已收敛超过总期限的待执行构建任务。",
            extra={"event": "project.build.job.overdue_pending_failed", "failed_count": recovered},
        )
    return recovered


async def recover_expired_build_jobs(
    session: AsyncSession,
    *,
    force_owner_prefix: str | None = None,
) -> int:
    """收敛租约过期的 running 任务：未超预算回 pending，超预算标 failed。

    多副本安全：默认只回收 lease_expires_at 为空或已过期的任务，不得抢走其它
    副本租约仍有效、正在执行的构建。`force_owner_prefix` 仅额外回收
    `lease_owner` 以该前缀开头的任务（同一主机/进程中断的自身任务）。
    回收时一律作废 attempt_id，阻止迟到上传把旧产物提升为最终结果。

    时序委托 `recover_expired_running_jobs` + `PROJECT_BUILD_VOCABULARY`；
    本函数只描述构建领域分类（产物已提升 / 超期 / 预算）与写入取值。
    """

    now = utc_now()
    normalized_prefix = str(force_owner_prefix or "").strip()
    recoverable_or = (
        [ProjectBuildJob.lease_owner.like(f"{normalized_prefix}%")] if normalized_prefix else None
    )

    # 候选列供 classify 读取：id 在前，其余为领域字段。
    candidate_columns = [
        ProjectBuildJob.id,
        ProjectBuildJob.attempt_count,
        ProjectBuildJob.max_attempts,
        ProjectBuildJob.deadline_at,
        ProjectBuildJob.artifact_storage_key,
    ]

    def _classify(row: Row[Any], attempt_limit_fallback: int) -> str:
        # 产物已提升：按成功收敛，不得清空产物后再重派。
        if row[4]:
            return "succeeded"
        attempt_limit = int(row[2] or 3)
        attempt_count = int(row[1] or 0)
        deadline_at: datetime | None = row[3]
        past_deadline = deadline_at is not None and now >= deadline_at
        if attempt_count < attempt_limit and not past_deadline:
            return "requeued"
        return "failed"

    def _recover_values(kind: str, row: Row[Any], recovered_at: datetime) -> dict[str, Any]:
        clear_fields = _clear_artifact_fields()
        if kind == "succeeded":
            return {
                "status": "succeeded",
                "lease_owner": None,
                "lease_expires_at": None,
                "claimed_at": None,
                "error_message": None,
                "finished_at": recovered_at,
            }
        if kind == "requeued":
            return {
                "status": "pending",
                "lease_owner": None,
                "lease_expires_at": None,
                "claimed_at": None,
                # 作废 attempt 身份：旧令牌不得再把迟到产物提升为最终结果。
                "attempt_id": None,
                "error_message": "构建租约过期或进程中断，已回到待执行队列。",
                "finished_at": None,
                **clear_fields,
            }
        return {
            "status": "failed",
            "error_message": "构建进程中断或超时，且已用尽重试预算。",
            "finished_at": recovered_at,
            "lease_expires_at": None,
            "lease_owner": None,
            "claimed_at": None,
            "attempt_id": None,
            **clear_fields,
        }

    def _kind_extra_where(kind: str) -> list[Any]:
        if kind == "succeeded":
            return [ProjectBuildJob.artifact_storage_key.is_not(None)]
        return [ProjectBuildJob.artifact_storage_key.is_(None)]

    summary = await recover_expired_running_jobs(
        session,
        ProjectBuildJob,
        max_attempts=10**9,  # 预算由 classify 按行 max_attempts 判定
        interrupted_error_code="BUILD_LEASE_EXPIRED",
        interrupted_error_message="构建进程中断或超时，且已用尽重试预算。",
        now=now,
        vocabulary=PROJECT_BUILD_VOCABULARY,
        recover_values=_recover_values,
        classify_recovery=_classify,
        recoverable_or_conditions=recoverable_or,
        candidate_columns=candidate_columns,
        kind_extra_where=_kind_extra_where,
    )
    # 历史返回值语义：本次发生状态迁移的行数（含产物已提升的 succeeded）。
    return summary.total_count


async def recover_interrupted_build_jobs_on_startup(
    session_factory,
    *,
    owner_prefix: str | None = None,
) -> int:
    """应用启动时收敛租约过期或属于本进程前缀的构建任务。

    多副本下禁止使用全局 force 抢占：任何 Backend 启动（扩容、滚动发布、崩溃重启）
    都只应收回过期租约与本进程前缀任务，避免重复派发其它副本正在执行的构建。
    """

    async with session_factory() as session:
        recovered = await recover_expired_build_jobs(session, force_owner_prefix=owner_prefix)
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


def _normalize_build_entry_file(raw_entry_file: str | None) -> str:
    """规范化构建产物入口文件名，仅允许相对文件路径。"""

    normalized = str(raw_entry_file or "").strip().replace("\\", "/")
    if not normalized:
        raise AppException(status_code=400, code="BUILD_ARTIFACT_ENTRY_FILE_INVALID", detail="构建产物入口文件不能为空。")
    if not normalized.isascii():
        # 归档元数据经 HTTP 头传递，非 ASCII 头值只会被按 latin-1 解码成乱码，宁可拒绝也不留下错误的入口名。
        raise AppException(status_code=400, code="BUILD_ARTIFACT_ENTRY_FILE_INVALID", detail="构建产物入口文件只能使用 ASCII 字符。")
    if normalized.startswith("/") or ".." in Path(normalized).parts:
        raise AppException(status_code=400, code="BUILD_ARTIFACT_ENTRY_FILE_INVALID", detail="构建产物入口文件路径不合法。")
    return normalized
