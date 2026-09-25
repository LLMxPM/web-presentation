"""文件功能：管理资源渲染提示回填任务队列、任务组进度和后台执行循环。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import Iterable
from time import monotonic
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.asset_render_hint_backfill_job import AssetRenderHintBackfillJob
from app.models.enums import AssetType, RecordStatus
from app.schemas.asset import (
    AssetRenderHintBackfillFailure,
    AssetRenderHintBackfillJobGroupResponse,
    AssetRenderHintBackfillJobResponse,
    resolve_asset_content_editable,
)
from app.services.asset_render_hint_measurement_service import AssetRenderHintMeasurementService
from app.services.asset_render_metadata_service import AssetRenderMetadataService
from app.services.asset_service import AssetService
from app.services.auth_service import AuthContext
from app.services.durable_job_lease_service import (
    build_durable_worker_id,
    claim_pending_jobs as claim_durable_jobs,
    recover_expired_running_jobs,
    renew_running_job_lease,
    transition_owned_running_job,
)
from app.services.workspace_service import WorkspaceService


ACTIVE_BACKFILL_JOB_STATUSES = ("pending", "running")
TERMINAL_BACKFILL_JOB_STATUSES = {"succeeded", "failed", "skipped"}
# 与 mutation_job_max_attempts / durable_job 口径一致：判定用 attempt_count < max，共 3 次执行机会。
MAX_BACKFILL_JOB_ATTEMPTS = 3
BACKFILL_RUNTIME_TYPES = {AssetType.FORMULA, AssetType.MERMAID}
BACKFILL_STATIC_TYPES = {AssetType.IMAGE, AssetType.VIDEO, AssetType.DRAWIO}
BACKFILL_SUPPORTED_TYPES = BACKFILL_RUNTIME_TYPES | BACKFILL_STATIC_TYPES
BACKFILL_JOB_INTERRUPTED_ERROR_CODE = "ASSET_RENDER_HINT_BACKFILL_JOB_INTERRUPTED"
logger = logging.getLogger(__name__)


class AssetRenderHintBackfillJobService:
    """资源渲染提示回填任务服务，负责创建、查询和执行队列任务。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        measurement_service: AssetRenderHintMeasurementService | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.asset_service = AssetService(session)
        self.measurement_service = measurement_service or AssetRenderHintMeasurementService()
        self.workspace_service = WorkspaceService(session)

    async def create_backfill_jobs(
        self,
        *,
        workspace_id: int,
        current: AuthContext,
        asset_types: Iterable[AssetType | str] | None = None,
        asset_ids: Iterable[int] | None = None,
        mode: str = "preview",
        overwrite_manual: bool = False,
        source: str = "manual",
    ) -> AssetRenderHintBackfillJobGroupResponse:
        """为工作空间资源创建比例回填任务组。"""

        await self.workspace_service.ensure_access(workspace_id, user_id=current.user.id)
        normalized_mode = self._normalize_mode(mode)
        normalized_types = self._normalize_asset_types(asset_types)
        normalized_asset_ids = self._normalize_asset_ids(asset_ids)
        assets = await self._list_target_assets(
            workspace_id=workspace_id,
            asset_types=normalized_types,
            asset_ids=normalized_asset_ids,
        )
        group_id = uuid.uuid4().hex
        jobs: list[AssetRenderHintBackfillJob] = []
        for asset in assets:
            job = AssetRenderHintBackfillJob(
                job_group_id=group_id,
                workspace_id=asset.workspace_id,
                asset_id=asset.id,
                asset_type=asset.asset_type,
                source=source,
                mode=normalized_mode,
                overwrite_manual=overwrite_manual,
                status="pending",
                attempt_count=0,
                current_render_metadata=asset.render_metadata,
                next_render_metadata=None,
                created_by=current.user.id,
            )
            self.session.add(job)
            jobs.append(job)
        if jobs:
            await self.session.commit()
            jobs = await self._list_jobs_by_ids([job.id for job in jobs])
        return await self._build_group_response(group_id=group_id, jobs=jobs)

    async def get_group_response(self, *, group_id: str, current: AuthContext) -> AssetRenderHintBackfillJobGroupResponse:
        """读取资源比例回填任务组聚合进度，并校验当前用户有工作空间访问权。"""

        jobs = await self._list_jobs_by_group_id(group_id)
        if not jobs:
            raise AppException(status_code=404, code="ASSET_RENDER_HINT_BACKFILL_JOB_GROUP_NOT_FOUND", detail="资源比例回填任务组不存在。")
        checked_workspace_ids: set[int] = set()
        for job in jobs:
            if job.workspace_id in checked_workspace_ids:
                continue
            await self.workspace_service.ensure_access(job.workspace_id, user_id=current.user.id)
            checked_workspace_ids.add(job.workspace_id)
        return await self._build_group_response(group_id=group_id, jobs=jobs)

    async def get_job_by_id(self, job_id: int) -> AssetRenderHintBackfillJob:
        """按 ID 读取资源比例回填任务。"""

        stmt = select(AssetRenderHintBackfillJob).where(AssetRenderHintBackfillJob.id == job_id)
        job = (await self.session.execute(stmt)).scalar_one_or_none()
        if job is None:
            raise AppException(status_code=404, code="ASSET_RENDER_HINT_BACKFILL_JOB_NOT_FOUND", detail="资源比例回填任务不存在。")
        return job

    async def claim_pending_jobs(self, *, limit: int, worker_id: str) -> list[AssetRenderHintBackfillJob]:
        """以数据库条件更新原子领取待执行任务，并写入本次 attempt 身份与租约。

        领取正确性只依赖主库：两个并发领取者对同一任务的 UPDATE 条件都要求
        `status='pending'`，因此最多一个成功；运行态被清空不影响领取结果。
        """

        job_ids = await claim_durable_jobs(
            self.session,
            AssetRenderHintBackfillJob,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=self.settings.asset_render_hint_backfill_job_lease_seconds,
        )
        if not job_ids:
            return []
        return await self._list_jobs_by_ids(job_ids)

    async def run_claimed_job(self, job_id: int, *, worker_id: str | None = None) -> None:
        """执行一个已领取的资源比例回填任务，并以 attempt 围栏持久化终态。"""

        job = await self.get_job_by_id(job_id)
        owner = worker_id or job.worker_id
        if job.status != "running" or not owner or job.worker_id != owner:
            return
        try:
            asset = await self.asset_service._get_asset_or_raise(job.workspace_id, job.asset_id)
            self._ensure_job_still_targets_asset(job, asset)
            current_metadata = asset.render_metadata
            if AssetRenderMetadataService.is_manual_metadata(current_metadata) and not job.overwrite_manual:
                await self._commit_job_result(
                    job_id=job_id,
                    worker_id=owner,
                    status="skipped",
                    current_render_metadata=current_metadata,
                    error_code=None,
                    error_message="资源比例来自人工或资源助手维护，已跳过自动回填。",
                )
                return

            content = await self.asset_service.driver.read_content(asset.workspace_id, asset.file_name)
            next_metadata = await self.measurement_service.measure_metadata(asset=asset, content=content)
            if next_metadata is None:
                await self._commit_job_result(
                    job_id=job_id,
                    worker_id=owner,
                    status="skipped",
                    current_render_metadata=current_metadata,
                    error_code=None,
                    error_message="未能从资源内容推断近似比例。",
                )
                return

            if next_metadata == current_metadata:
                await self._commit_job_result(
                    job_id=job_id,
                    worker_id=owner,
                    status="skipped",
                    current_render_metadata=current_metadata,
                    next_render_metadata=next_metadata,
                    error_code=None,
                    error_message="资源近似比例已是最新。",
                )
                return

            committed = await self._commit_job_result(
                job_id=job_id,
                worker_id=owner,
                status="succeeded",
                current_render_metadata=current_metadata,
                next_render_metadata=next_metadata,
                apply_render_metadata=next_metadata if job.mode == "apply" else None,
                apply_asset_id=job.asset_id,
                apply_workspace_id=job.workspace_id,
                error_code=None,
                error_message=None,
            )
            if committed:
                logger.info(
                    "资源比例回填任务执行成功。",
                    extra={"event": "asset.render_hint.backfill.job.succeeded", "job_id": job_id, "asset_id": job.asset_id},
                )
            else:
                logger.info(
                    "资源比例回填任务迟到成功结果被围栏拒绝。",
                    extra={"event": "asset.render_hint.backfill.job.stale_result_rejected", "job_id": job_id},
                )
        except Exception as error:  # noqa: BLE001
            await self._mark_job_failed_or_retry(job_id=job_id, worker_id=owner, error=error)
            logger.exception(
                "资源比例回填任务执行失败。",
                extra={"event": "asset.render_hint.backfill.job.failed", "job_id": job_id, "asset_id": job.asset_id},
            )

    async def recover_interrupted_jobs(self) -> int:
        """恢复租约为空或已过期的 running 任务。

        仍在租约期内的 running 可能正被本进程或（PostgreSQL 多进程部署下）其它
        Backend 执行，无条件回收会重复执行；超出租约且未耗尽重试预算的任务会
        回到 pending 等待下一次 attempt，因此迟到的旧 attempt 结果会被围栏拒绝。
        """

        summary = await recover_expired_running_jobs(
            self.session,
            AssetRenderHintBackfillJob,
            max_attempts=MAX_BACKFILL_JOB_ATTEMPTS,
            interrupted_error_code=BACKFILL_JOB_INTERRUPTED_ERROR_CODE,
            interrupted_error_message="资源比例回填任务因服务重启或租约过期中断。",
        )
        return summary.total_count

    async def _commit_job_result(
        self,
        *,
        job_id: int,
        worker_id: str,
        status: str,
        error_code: str | None,
        error_message: str | None,
        current_render_metadata: dict[str, Any] | None = None,
        next_render_metadata: dict[str, Any] | None = None,
        apply_render_metadata: dict[str, Any] | None = None,
        apply_asset_id: int | None = None,
        apply_workspace_id: int | None = None,
    ) -> bool:
        """续租后按 attempt 身份、running 状态与有效租约提交终态。

        资源比例写入与任务终态在同一事务内完成：任一条件不满足时旧 attempt 的
        迟到结果都会被拒绝，不会覆盖新 attempt 的状态或资源元数据。
        """

        await self.session.rollback()
        lease_seconds = self.settings.asset_render_hint_backfill_job_lease_seconds
        renewed = await renew_running_job_lease(
            self.session,
            AssetRenderHintBackfillJob,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if not renewed:
            logger.info(
                "资源比例回填任务租约已失效，终态提交被围栏拒绝。",
                extra={"event": "asset.render_hint.backfill.job.lease_lost", "job_id": job_id},
            )
            return False

        values: dict[str, Any] = {
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "next_render_metadata": next_render_metadata,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "finished_at": utc_now(),
        }
        if current_render_metadata is not None:
            values["current_render_metadata"] = current_render_metadata
        committed = await transition_owned_running_job(
            self.session,
            AssetRenderHintBackfillJob,
            job_id=job_id,
            worker_id=worker_id,
            values=values,
            require_active_lease=True,
            commit=False,
        )
        if not committed:
            await self.session.rollback()
            return False
        if apply_render_metadata is not None and apply_asset_id is not None and apply_workspace_id is not None:
            asset = await self.asset_service._get_asset_or_raise(apply_workspace_id, apply_asset_id)
            asset.render_metadata = apply_render_metadata
        await self.session.commit()
        return True

    async def _mark_job_failed_or_retry(self, *, job_id: int, worker_id: str, error: Exception) -> None:
        """把异常压缩为回填任务失败状态；仍有重试预算时回到 pending 等待新 attempt。"""

        await self.session.rollback()
        job = (
            await self.session.execute(
                select(AssetRenderHintBackfillJob).where(AssetRenderHintBackfillJob.id == job_id)
            )
        ).scalar_one_or_none()
        if job is None:
            return
        error_code, error_message = self._describe_error(error)
        retryable = self._is_retryable_error(error) and int(job.attempt_count) < MAX_BACKFILL_JOB_ATTEMPTS
        values: dict[str, Any] = {
            "error_code": error_code,
            "error_message": error_message,
            "lease_expires_at": None,
            "heartbeat_at": None,
        }
        if retryable:
            values.update({"status": "pending", "worker_id": None, "started_at": None, "finished_at": None})
        else:
            values.update({"status": "failed", "finished_at": utc_now()})
        committed = await transition_owned_running_job(
            self.session,
            AssetRenderHintBackfillJob,
            job_id=job_id,
            worker_id=worker_id,
            values=values,
        )
        if not committed:
            logger.info(
                "资源比例回填任务迟到失败结果被围栏拒绝。",
                extra={"event": "asset.render_hint.backfill.job.stale_result_rejected", "job_id": job_id},
            )

    async def _list_target_assets(
        self,
        *,
        workspace_id: int,
        asset_types: set[AssetType],
        asset_ids: set[int] | None,
    ) -> list[WorkspaceAsset]:
        """按回填范围读取符合条件的资源。"""

        stmt = (
            select(WorkspaceAsset)
            .where(
                WorkspaceAsset.workspace_id == workspace_id,
                WorkspaceAsset.status == RecordStatus.ACTIVE.value,
                WorkspaceAsset.history_kind.is_(None),
                WorkspaceAsset.asset_type.in_([item.value for item in asset_types]),
            )
            .order_by(WorkspaceAsset.id.asc())
        )
        if asset_ids is not None:
            if not asset_ids:
                return []
            stmt = stmt.where(WorkspaceAsset.id.in_(asset_ids))
        assets = list((await self.session.execute(stmt)).scalars().all())
        return [
            asset for asset in assets
            if self._is_asset_backfill_readable(asset)
        ]

    async def _list_jobs_by_ids(self, job_ids: Iterable[int]) -> list[AssetRenderHintBackfillJob]:
        """按 ID 列表读取任务。"""

        ids = [int(job_id) for job_id in job_ids]
        if not ids:
            return []
        stmt = select(AssetRenderHintBackfillJob).where(AssetRenderHintBackfillJob.id.in_(ids)).order_by(AssetRenderHintBackfillJob.id.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def _list_jobs_by_group_id(self, group_id: str) -> list[AssetRenderHintBackfillJob]:
        """按任务组 ID 读取任务。"""

        stmt = (
            select(AssetRenderHintBackfillJob)
            .where(AssetRenderHintBackfillJob.job_group_id == group_id)
            .order_by(AssetRenderHintBackfillJob.created_at.asc(), AssetRenderHintBackfillJob.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _build_group_response(
        self,
        *,
        group_id: str,
        jobs: list[AssetRenderHintBackfillJob],
    ) -> AssetRenderHintBackfillJobGroupResponse:
        """把一组任务聚合为前端可轮询的进度响应。"""

        asset_names = await self._build_asset_name_map(job.asset_id for job in jobs)
        counter = Counter(job.status for job in jobs)
        pending_count = counter.get("pending", 0)
        running_count = counter.get("running", 0)
        succeeded_count = counter.get("succeeded", 0)
        failed_count = counter.get("failed", 0)
        skipped_count = counter.get("skipped", 0)
        requested_count = len(jobs)
        if pending_count > 0:
            status = "pending"
        elif running_count > 0:
            status = "running"
        elif failed_count > 0 and succeeded_count + skipped_count > 0:
            status = "partial"
        elif failed_count > 0:
            status = "failed"
        else:
            status = "succeeded"
        responses = [self._build_job_response(job, asset_name=asset_names.get(job.asset_id)) for job in jobs]
        return AssetRenderHintBackfillJobGroupResponse(
            job_group_id=group_id,
            status=status,
            requested_count=requested_count,
            pending_count=pending_count,
            running_count=running_count,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            asset_ids=[job.asset_id for job in jobs if job.status == "succeeded" and job.next_render_metadata],
            jobs=responses,
            failures=[
                AssetRenderHintBackfillFailure(
                    asset_id=job.asset_id,
                    asset_name=asset_names.get(job.asset_id),
                    code=job.error_code or str(job.asset_id),
                    detail=job.error_message or "资源比例回填任务执行失败。",
                )
                for job in jobs
                if job.status == "failed"
            ],
        )

    def _build_job_response(
        self,
        job: AssetRenderHintBackfillJob,
        *,
        asset_name: str | None,
    ) -> AssetRenderHintBackfillJobResponse:
        """把任务模型转换为带比例摘要的响应。"""

        payload = AssetRenderHintBackfillJobResponse.model_validate(job).model_dump()
        payload["asset_name"] = asset_name
        payload["current_approx_aspect_ratio"] = AssetRenderMetadataService.summarize_metadata(job.current_render_metadata)["approx_aspect_ratio"]
        payload["next_approx_aspect_ratio"] = AssetRenderMetadataService.summarize_metadata(job.next_render_metadata)["approx_aspect_ratio"]
        return AssetRenderHintBackfillJobResponse.model_validate(payload)

    async def _build_asset_name_map(self, asset_ids: Iterable[int]) -> dict[int, str]:
        """批量读取任务对应资源名称。"""

        ids = sorted({int(asset_id) for asset_id in asset_ids})
        if not ids:
            return {}
        stmt = select(WorkspaceAsset.id, WorkspaceAsset.name).where(WorkspaceAsset.id.in_(ids))
        rows = (await self.session.execute(stmt)).all()
        return {int(row.id): str(row.name) for row in rows}

    @staticmethod
    def _describe_error(error: Exception) -> tuple[str, str]:
        """把异常压缩为可持久化的错误码与提示。"""

        if isinstance(error, AppException):
            return error.code, error.detail
        return "ASSET_RENDER_HINT_BACKFILL_JOB_FAILED", str(error) or "资源比例回填任务执行失败。"

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        """校验并规范化任务模式。"""

        normalized = str(mode or "").strip().lower()
        if normalized not in {"preview", "apply"}:
            raise AppException(status_code=400, code="ASSET_RENDER_HINT_BACKFILL_MODE_INVALID", detail="回填模式只能是 preview 或 apply。")
        return normalized

    @staticmethod
    def _normalize_asset_types(asset_types: Iterable[AssetType | str] | None) -> set[AssetType]:
        """校验并规范化回填资源类型。"""

        if asset_types is None:
            return set(BACKFILL_SUPPORTED_TYPES)
        resolved: set[AssetType] = set()
        for item in asset_types:
            try:
                asset_type = item if isinstance(item, AssetType) else AssetType(str(item))
            except ValueError as exc:
                raise AppException(status_code=400, code="ASSET_TYPE_INVALID", detail="资源类型不合法。") from exc
            if asset_type not in BACKFILL_SUPPORTED_TYPES:
                raise AppException(status_code=400, code="ASSET_RENDER_HINT_BACKFILL_TYPE_UNSUPPORTED", detail="回填比例仅支持图片、视频、Draw.io、Formula 和 Mermaid 资源。")
            resolved.add(asset_type)
        return resolved or set(BACKFILL_SUPPORTED_TYPES)

    @staticmethod
    def _normalize_asset_ids(asset_ids: Iterable[int] | None) -> set[int] | None:
        """规范化可选资源 ID 范围。"""

        if asset_ids is None:
            return None
        return {int(asset_id) for asset_id in asset_ids if int(asset_id) > 0}

    @staticmethod
    def _ensure_job_still_targets_asset(job: AssetRenderHintBackfillJob, asset: WorkspaceAsset) -> None:
        """确保异步任务执行时资源仍满足回填约束。"""

        if asset.status != RecordStatus.ACTIVE.value or asset.history_kind:
            raise AppException(status_code=409, code="ASSET_RENDER_HINT_BACKFILL_TARGET_INVALID", detail="资源状态已变化，无法继续回填比例。")
        if AssetType(asset.asset_type) not in BACKFILL_SUPPORTED_TYPES:
            raise AppException(status_code=409, code="ASSET_RENDER_HINT_BACKFILL_TYPE_CHANGED", detail="资源类型已变化，无法继续回填比例。")
        if str(asset.asset_type) != str(job.asset_type):
            raise AppException(status_code=409, code="ASSET_RENDER_HINT_BACKFILL_TYPE_CHANGED", detail="资源类型已变化，无法继续回填比例。")
        if not AssetRenderHintBackfillJobService._is_asset_backfill_readable(asset):
            raise AppException(status_code=409, code="ASSET_RENDER_HINT_BACKFILL_CONTENT_UNREADABLE", detail="资源内容不可读取，无法继续回填比例。")

    @staticmethod
    def _is_asset_backfill_readable(asset: WorkspaceAsset) -> bool:
        """判断资源内容是否可被比例回填任务读取。"""

        asset_type = AssetType(asset.asset_type)
        if asset_type in BACKFILL_STATIC_TYPES:
            return True
        return resolve_asset_content_editable(asset.asset_type, asset.original_name, asset.content_type)

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        """判断异常是否值得重试。"""

        if isinstance(error, AppException):
            return error.status_code >= 500
        return True


async def run_asset_render_hint_backfill_queue_loop(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """按配置持续领取并执行资源比例回填队列任务。"""

    settings = get_settings()
    factory = session_factory or get_session_factory()
    poll_interval = max(0.1, settings.asset_render_hint_backfill_queue_poll_interval_seconds)
    concurrency = max(1, settings.asset_render_hint_backfill_queue_concurrency)
    recovery_interval = max(1.0, min(float(settings.durable_job_heartbeat_seconds), 30.0))
    last_recovery_at = 0.0
    worker_id = build_durable_worker_id()
    logger.info(
        "资源比例回填队列后台任务已启动。",
        extra={"event": "asset.render_hint.backfill.queue.started", "concurrency": concurrency, "worker_id": worker_id},
    )
    while True:
        try:
            async with factory() as session:
                service = AssetRenderHintBackfillJobService(session)
                if monotonic() - last_recovery_at >= recovery_interval:
                    await service.recover_interrupted_jobs()
                    last_recovery_at = monotonic()
                claimed = await service.claim_pending_jobs(limit=concurrency, worker_id=worker_id)
            if not claimed:
                await asyncio.sleep(poll_interval)
                continue
            await asyncio.gather(
                *[
                    run_asset_render_hint_backfill_job(job.id, worker_id=worker_id, session_factory=factory)
                    for job in claimed
                ]
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("资源比例回填队列循环异常。", extra={"event": "asset.render_hint.backfill.queue.failed"})
            await asyncio.sleep(poll_interval)


async def run_asset_render_hint_backfill_job(
    job_id: int,
    *,
    worker_id: str | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """使用独立数据库会话执行单个资源比例回填任务。"""

    factory = session_factory or get_session_factory()
    async with factory() as session:
        await AssetRenderHintBackfillJobService(session).run_claimed_job(job_id, worker_id=worker_id)


async def recover_interrupted_asset_render_hint_backfill_jobs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    """应用启动时收敛租约过期的资源比例回填任务。"""

    async with session_factory() as session:
        recovered_count = await AssetRenderHintBackfillJobService(session).recover_interrupted_jobs()
    if recovered_count:
        logger.warning(
            "已恢复中断的资源比例回填任务。",
            extra={"event": "asset.render_hint.backfill.jobs.recovered", "count": recovered_count},
        )
    return recovered_count
