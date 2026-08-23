"""文件功能：管理异步 Mutation Job 生命周期、CAS 租约心跳、三阶段短事务 Worker 与后台回收器。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.text_normalizer import calculate_source_hash
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.api_mutation_job import ApiMutationJob
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from app.schemas.external_api import (
    ExternalComponentApplyEditsMutationRequest,
    ExternalComponentCreateMutationRequest,
    ExternalComponentMetadataMutationRequest,
    ExternalErrorDetail,
    ExternalMutationJobResponse,
    ExternalPageApplyEditsMutationRequest,
    ExternalPageCreateMutationRequest,
)
from app.schemas.page import PageCreateRequest, PageUpdateRequest
from app.schemas.component import (
    WorkspaceComponentCreateRequest,
    WorkspaceComponentUpdateRequest,
)
from app.services.durable_job_lease_service import build_durable_worker_id
from app.services.mutation_planners.component_mutation_planner import ComponentMutationPlanner
from app.services.mutation_planners.page_mutation_planner import PageMutationPlanner
from app.services.page_service import PageService
from app.services.workspace_component_service import WorkspaceComponentService

logger = logging.getLogger(__name__)

RETRYABLE_ERROR_CODES = {
    "RUNTIME_UNAVAILABLE",
    "CHROMIUM_TIMEOUT",
    "DATABASE_LOCK_TIMEOUT",
    "INTERNAL_NETWORK_ERROR",
}


class MutationJobService:
    """异步变更任务服务。"""

    def __init__(self, session: AsyncSession, *, worker_id: str | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.worker_id = worker_id or build_durable_worker_id()

    # ------------------ Enqueue Operations ------------------

    async def enqueue_page_create_job(
        self,
        *,
        workspace_id: int,
        user_id: int,
        payload: ExternalPageCreateMutationRequest,
        idempotency_record_id: int | None = None,
    ) -> ApiMutationJob:
        """入队页面创建异步任务。"""

        job = ApiMutationJob(
            job_id=f"job-{uuid.uuid4().hex}",
            job_type="page_create",
            workspace_id=workspace_id,
            created_by=user_id,
            idempotency_record_id=idempotency_record_id,
            status="pending",
            payload_json=payload.model_dump(mode="json"),
            max_attempts=self.settings.mutation_job_max_attempts,
            created_at=utc_now(),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    enqueue_page_create = enqueue_page_create_job

    async def enqueue_page_edit_job(
        self,
        *,
        workspace_id: int,
        user_id: int,
        payload: ExternalPageApplyEditsMutationRequest,
        idempotency_record_id: int | None = None,
    ) -> ApiMutationJob:
        """入队页面结构化编辑异步任务。"""

        job = ApiMutationJob(
            job_id=f"job-{uuid.uuid4().hex}",
            job_type="page_edit",
            workspace_id=workspace_id,
            target_id=payload.page_id,
            base_version_no=payload.base_version_no,
            created_by=user_id,
            idempotency_record_id=idempotency_record_id,
            status="pending",
            payload_json=payload.model_dump(mode="json"),
            max_attempts=self.settings.mutation_job_max_attempts,
            created_at=utc_now(),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    enqueue_page_apply_edits = enqueue_page_edit_job

    async def enqueue_component_create_job(
        self,
        *,
        workspace_id: int,
        user_id: int,
        payload: ExternalComponentCreateMutationRequest,
        idempotency_record_id: int | None = None,
    ) -> ApiMutationJob:
        """入队组件创建异步任务。"""

        job = ApiMutationJob(
            job_id=f"job-{uuid.uuid4().hex}",
            job_type="component_create",
            workspace_id=workspace_id,
            created_by=user_id,
            idempotency_record_id=idempotency_record_id,
            status="pending",
            payload_json=payload.model_dump(mode="json"),
            max_attempts=self.settings.mutation_job_max_attempts,
            created_at=utc_now(),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    enqueue_component_create = enqueue_component_create_job

    async def enqueue_component_edit_job(
        self,
        *,
        workspace_id: int,
        user_id: int,
        payload: ExternalComponentApplyEditsMutationRequest,
        idempotency_record_id: int | None = None,
    ) -> ApiMutationJob:
        """入队组件结构化编辑异步任务。"""

        base_ver = getattr(payload, "base_version_no", None)
        base_draft_hash = getattr(payload, "base_draft_hash", None)
        job = ApiMutationJob(
            job_id=f"job-{uuid.uuid4().hex}",
            job_type="component_edit",
            workspace_id=workspace_id,
            target_id=payload.component_id,
            base_version_no=base_ver,
            source_hash=base_draft_hash,
            created_by=user_id,
            idempotency_record_id=idempotency_record_id,
            status="pending",
            payload_json=payload.model_dump(mode="json"),
            max_attempts=self.settings.mutation_job_max_attempts,
            created_at=utc_now(),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    enqueue_component_apply_edits = enqueue_component_edit_job

    async def enqueue_component_metadata_job(
        self,
        *,
        workspace_id: int,
        user_id: int,
        payload: ExternalComponentMetadataMutationRequest,
        idempotency_record_id: int | None = None,
    ) -> ApiMutationJob:
        """入队组件元数据重校验与更新任务。"""

        job = ApiMutationJob(
            job_id=f"job-{uuid.uuid4().hex}",
            job_type="component_metadata",
            workspace_id=workspace_id,
            target_id=payload.component_id,
            base_version_no=payload.base_version_no,
            source_hash=payload.base_draft_hash,
            created_by=user_id,
            idempotency_record_id=idempotency_record_id,
            status="pending",
            payload_json=payload.model_dump(mode="json"),
            max_attempts=self.settings.mutation_job_max_attempts,
            created_at=utc_now(),
        )
        self.session.add(job)
        await self.session.flush()
        return job

    # ------------------ Query & Cancel ------------------

    async def get_job_by_public_id(self, job_id: str) -> ApiMutationJob | None:
        """根据公开 job_id 查询任务。"""

        return await self.session.scalar(select(ApiMutationJob).where(ApiMutationJob.job_id == job_id))

    async def get_job_response(self, job: ApiMutationJob) -> ExternalMutationJobResponse:
        """将内部 Job 模型映射为外部 API 统一状态响应。"""

        err_detail = None
        if job.error_json:
            err_detail = ExternalErrorDetail.model_validate(job.error_json)

        retry_of_public_id = None
        if job.retry_of_job_id is not None:
            retry_of_public_id = await self.session.scalar(
                select(ApiMutationJob.job_id).where(ApiMutationJob.id == job.retry_of_job_id)
            )

        return ExternalMutationJobResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            workspace_id=job.workspace_id,
            target_id=job.target_id,
            status=job.status,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            next_attempt_at=job.next_attempt_at,
            last_error_code=job.last_error_code,
            cancel_requested_at=job.cancel_requested_at,
            retry_of_job_id=retry_of_public_id,
            result=job.result_json,
            error=err_detail,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    async def request_cancel_job(
        self,
        job: ApiMutationJob,
        *,
        commit: bool = True,
    ) -> tuple[int, ExternalMutationJobResponse]:
        """请求取消异步变更任务（使用 CAS 条件更新状态，防止覆盖并发终态）。"""

        if job.status == "canceled":
            return 200, await self.get_job_response(job)
        if job.status in {"succeeded", "failed"}:
            raise AppException(
                status_code=409,
                code="MUTATION_JOB_NOT_CANCELABLE",
                detail=f"状态为 {job.status} 的 Mutation 任务不能取消。",
            )

        now = utc_now()
        # 1. 尝试原子将 pending 转换为 canceled
        stmt = (
            update(ApiMutationJob)
            .where(ApiMutationJob.id == job.id)
            .where(ApiMutationJob.status == "pending")
            .values(
                status="canceled",
                finished_at=now,
                cancel_requested_at=now,
            )
        )
        res = await self.session.execute(stmt)
        if res.rowcount > 0:
            await self._commit_or_flush(commit)
            await self.session.refresh(job)
            return 200, await self.get_job_response(job)

        # 2. 若任务处于 running，原子打标 cancel_requested_at 等待 Worker 安全收敛
        stmt = (
            update(ApiMutationJob)
            .where(ApiMutationJob.id == job.id)
            .where(ApiMutationJob.status == "running")
            .values(cancel_requested_at=now)
        )
        res = await self.session.execute(stmt)
        if res.rowcount == 0:
            await self.session.refresh(job)
            return await self.request_cancel_job(job, commit=commit)
        await self._commit_or_flush(commit)
        await self.session.refresh(job)
        return 202, await self.get_job_response(job)

    async def enqueue_retry_job(
        self,
        job: ApiMutationJob,
        *,
        user_id: int,
        idempotency_record_id: int | None,
    ) -> ApiMutationJob:
        """为可重试失败任务创建不可变的新任务，保留原始 payload 与乐观锁基线。"""

        retryable = bool((job.error_json or {}).get("retryable"))
        if job.status != "failed" or not retryable:
            raise AppException(
                status_code=409,
                code="MUTATION_JOB_NOT_RETRYABLE",
                detail="仅允许重试处于 failed 且错误标记为 retryable 的 Mutation 任务。",
            )
        retried = ApiMutationJob(
            job_id=f"job-{uuid.uuid4().hex}",
            job_type=job.job_type,
            workspace_id=job.workspace_id,
            target_id=job.target_id,
            base_version_no=job.base_version_no,
            source_hash=job.source_hash,
            status="pending",
            payload_json=dict(job.payload_json or {}),
            idempotency_record_id=idempotency_record_id,
            retry_of_job_id=job.id,
            created_by=user_id,
            max_attempts=job.max_attempts,
            created_at=utc_now(),
        )
        self.session.add(retried)
        await self.session.flush()
        return retried

    async def _commit_or_flush(self, commit: bool) -> None:
        """按调用方事务边界提交或仅刷新当前 Session。"""

        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    # ------------------ Three-Phase Worker Execution ------------------

    async def claim_next_pending_job(self) -> ApiMutationJob | None:
        """阶段 1：短事务认领 pending 任务并抢占租约（通过 CAS 条件更新保证跨数据库多 Worker 并发安全）。"""

        now = utc_now()
        lease_seconds = self.settings.mutation_job_lease_seconds
        expires_at = now + timedelta(seconds=lease_seconds)

        # 1. 查找候选待认领任务 ID 列表
        candidate_stmt = (
            select(ApiMutationJob.id, ApiMutationJob.lease_generation)
            .where(ApiMutationJob.status == "pending")
            .where(
                or_(
                    ApiMutationJob.next_attempt_at.is_(None),
                    ApiMutationJob.next_attempt_at <= now,
                )
            )
            .order_by(ApiMutationJob.created_at.asc())
            .limit(10)
        )
        candidates = (await self.session.execute(candidate_stmt)).all()
        if not candidates:
            return None

        # 2. 对候选任务使用 CAS UPDATE 原子抢占单个任务
        for cand_id, cand_gen in candidates:
            update_stmt = (
                update(ApiMutationJob)
                .where(ApiMutationJob.id == cand_id)
                .where(ApiMutationJob.status == "pending")
                .where(ApiMutationJob.lease_generation == cand_gen)
                .values(
                    status="running",
                    worker_id=self.worker_id,
                    lease_generation=(cand_gen or 0) + 1,
                    lease_expires_at=expires_at,
                    heartbeat_at=now,
                    started_at=func.coalesce(ApiMutationJob.started_at, now),
                )
            )
            res = await self.session.execute(update_stmt)
            if res.rowcount > 0:
                await self.session.commit()
                claimed = await self.session.get(ApiMutationJob, cand_id)
                if claimed is not None:
                    await self.session.refresh(claimed)
                return claimed

        return None

    async def execute_job_with_lease(self, job: ApiMutationJob) -> None:
        """执行完整三阶段任务：启动心跳、事务外规划慢诊断、CAS 短事务写库收尾。"""

        generation = job.lease_generation
        job_id = job.id
        stop_heartbeat = asyncio.Event()

        # 启动租约心跳后台任务 (每 15s 心跳一次)
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(job_id, generation, stop_heartbeat)
        )

        try:
            # 阶段 2：在事务外调用 Planner 执行 AST 扫描与 Chromium 慢诊断
            planner_result = await self._run_planner_phase(job)

            # 阶段 3：短事务 CAS 校验并写入数据库
            await self._finalize_success(job_id, generation, planner_result)
        except AppException as app_err:
            await self._handle_job_failure(job_id, generation, app_err)
        except Exception as exc:
            logger.exception("Mutation 任务发生未捕获异常: %s", exc)
            fallback_err = AppException(status_code=500, code="INTERNAL_MUTATION_ERROR", detail=str(exc))
            await self._handle_job_failure(job_id, generation, fallback_err)
        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _heartbeat_loop(self, job_id: int, generation: int, stop_event: asyncio.Event) -> None:
        """CAS 周期性租约续期循环。"""

        interval = self.settings.mutation_job_heartbeat_seconds
        lease_seconds = self.settings.mutation_job_lease_seconds
        session_factory = get_session_factory()

        while not stop_event.is_set():
            try:
                await asyncio.sleep(interval)
                if stop_event.is_set():
                    break

                now = utc_now()
                expires_at = now + timedelta(seconds=lease_seconds)

                async with session_factory() as session:
                    stmt = (
                        update(ApiMutationJob)
                        .where(ApiMutationJob.id == job_id)
                        .where(ApiMutationJob.status == "running")
                        .where(ApiMutationJob.worker_id == self.worker_id)
                        .where(ApiMutationJob.lease_generation == generation)
                        .values(lease_expires_at=expires_at, heartbeat_at=now)
                    )
                    res = await session.execute(stmt)
                    await session.commit()
                    if res.rowcount == 0:
                        logger.warning("Mutation 租约续期失败，可能已失守或被回收 (ID: %s)", job_id)
                        break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Mutation 任务续期心跳异常: %s", exc)

    async def _run_planner_phase(self, job: ApiMutationJob) -> Any:
        """执行事务外的 Planner 慢诊断。"""

        payload = job.payload_json or {}
        session_factory = get_session_factory()

        async with session_factory() as session:
            if job.job_type == "page_create":
                planner = PageMutationPlanner(session)
                return await planner.plan_create(
                    workspace_id=job.workspace_id,
                    project_id=payload["project_id"],
                    user_id=job.created_by,
                    title=payload.get("name") or payload.get("title") or "新页面",
                    page_content=payload.get("source_code") or payload.get("page_content") or "",
                    summary=payload.get("description") or payload.get("summary"),
                )
            elif job.job_type == "page_edit":
                planner = PageMutationPlanner(session)
                page_detail = await PageService(session).get(payload["page_id"], user_id=job.created_by)
                return await planner.plan_apply_edits(
                    workspace_id=job.workspace_id,
                    project_id=page_detail.project_id,
                    page_id=payload["page_id"],
                    base_version_no=payload["base_version_no"],
                    user_id=job.created_by,
                    edits=payload["edits"],
                )
            elif job.job_type == "component_create":
                planner = ComponentMutationPlanner(session)
                return await planner.plan_create(
                    workspace_id=job.workspace_id,
                    user_id=job.created_by,
                    import_name=payload["import_name"],
                    name=payload["name"],
                    content=payload.get("source_code") or payload.get("content") or "",
                    component_type=payload.get("component_type", "custom"),
                    summary=payload.get("description") or payload.get("summary"),
                    preview_schema=payload.get("preview_schema"),
                )
            elif job.job_type == "component_edit":
                planner = ComponentMutationPlanner(session)
                comp = await WorkspaceComponentService(session).get(payload["component_id"], user_id=job.created_by)
                base_draft_hash = job.source_hash or payload.get("base_draft_hash") or calculate_source_hash(comp.content)
                return await planner.plan_apply_edits(
                    workspace_id=job.workspace_id,
                    user_id=job.created_by,
                    component_id=payload["component_id"],
                    base_draft_hash=base_draft_hash,
                    base_published_version_no=payload.get("base_version_no", comp.current_version_no or 0),
                    edits=payload["edits"],
                )
            elif job.job_type == "component_metadata":
                planner = ComponentMutationPlanner(session)
                comp = await WorkspaceComponentService(session).get(payload["component_id"], user_id=job.created_by)
                base_hash = job.source_hash or payload.get("base_draft_hash") or calculate_source_hash(comp.content)
                return await planner.plan_update_metadata(
                    workspace_id=job.workspace_id,
                    user_id=job.created_by,
                    component_id=payload["component_id"],
                    base_draft_hash=base_hash,
                    base_version_no=job.base_version_no or payload.get("base_version_no") or comp.current_version_no,
                    name=payload.get("name"),
                    import_name=payload.get("import_name"),
                    component_type=payload.get("component_type"),
                    summary=payload.get("summary"),
                    preview_schema=payload.get("preview_schema"),
                    change_note=payload.get("change_note"),
                )
            else:
                raise AppException(status_code=400, code="UNKNOWN_JOB_TYPE", detail=f"未知任务类型: {job.job_type}")

    async def _finalize_success(self, job_id: int, generation: int, plan_result: Any) -> None:
        """阶段 3：在短事务中校验 CAS 围栏、调用 Service 写入实体并标记成功。"""

        if not getattr(plan_result, "success", True):
            error_code = getattr(plan_result, "error_code", None) or "VALIDATION_FAILED"
            error_msg = getattr(plan_result, "error_message", None) or getattr(plan_result, "message", "代码校验未通过")
            raise AppException(status_code=422, code=error_code, detail=error_msg)

        now = utc_now()
        session_factory = get_session_factory()

        async with session_factory() as session:
            # 1. CAS 锁定任务行
            stmt = (
                select(ApiMutationJob)
                .where(ApiMutationJob.id == job_id)
                .where(ApiMutationJob.status == "running")
                .where(ApiMutationJob.worker_id == self.worker_id)
                .where(ApiMutationJob.lease_generation == generation)
                .where(ApiMutationJob.lease_expires_at > now)
                .with_for_update()
            )
            job = await session.scalar(stmt)
            if job is None:
                logger.error("Mutation 阶段 3 CAS 围栏失效 (ID: %s, gen: %s)", job_id, generation)
                return

            # 若收到取消请求，收敛为 canceled
            if job.cancel_requested_at is not None:
                job.status = "canceled"
                job.finished_at = now
                await session.commit()
                return

            # 2. 执行 Service 写入 (commit=False)
            target_id: int | None = None
            result_dict: dict[str, Any] = {}

            if job.job_type == "page_create":
                page_req = PageCreateRequest(
                    workspace_id=job.workspace_id,
                    project_id=job.payload_json["project_id"],
                    title=plan_result.title or job.payload_json.get("name") or "新页面",
                    page_content=plan_result.prepared_content,
                    summary=plan_result.summary,
                )
                created_page = await PageService(session).create(
                    payload=page_req,
                    operator_id=job.created_by,
                    commit=False,
                )
                target_id = created_page.id
                result_dict = {
                    "page_id": created_page.id,
                    "page_code": created_page.code,
                    "version_no": created_page.current_version_no,
                }
            elif job.job_type == "page_edit":
                target_page_id = plan_result.target_page_id or job.payload_json["page_id"]
                base_version = job.base_version_no or job.payload_json.get("base_version_no")
                page_lock_stmt = select(Page).where(Page.id == target_page_id).with_for_update()
                locked_page = await session.scalar(page_lock_stmt)
                if locked_page is None:
                    raise AppException(status_code=404, code="PAGE_NOT_FOUND", detail="页面不存在。")
                page_service = PageService(session)
                current_page = await page_service.get(target_page_id, user_id=job.created_by)
                if base_version is not None and current_page.current_version_no != base_version:
                    raise AppException(
                        status_code=409,
                        code="PAGE_CONCURRENT_MODIFIED",
                        detail=f"页面版本已在诊断期间发生变更 (基准版本: {base_version}，最新版本: {current_page.current_version_no})，放弃覆盖。",
                    )

                page_update_req = PageUpdateRequest(
                    page_content=plan_result.prepared_content,
                )
                updated_page = await page_service.update(
                    page_id=target_page_id,
                    payload=page_update_req,
                    operator_id=job.created_by,
                    commit=False,
                )
                target_id = updated_page.id
                result_dict = {
                    "page_id": updated_page.id,
                    "version_no": updated_page.current_version_no,
                }
            elif job.job_type == "component_create":
                comp_req = WorkspaceComponentCreateRequest(
                    workspace_id=job.workspace_id,
                    import_name=plan_result.import_name or job.payload_json["import_name"],
                    name=plan_result.name or job.payload_json["name"],
                    component_type=plan_result.component_type,
                    content=plan_result.prepared_content,
                    summary=plan_result.summary,
                    preview_schema=plan_result.preview_schema,
                )
                created_comp = await WorkspaceComponentService(session).create(
                    payload=comp_req,
                    operator_id=job.created_by,
                    commit=False,
                )
                target_id = created_comp.id
                result_dict = {
                    "component_id": created_comp.id,
                    "import_name": created_comp.import_name,
                    "version_no": created_comp.current_version_no,
                }
            elif job.job_type == "component_edit":
                target_comp_id = plan_result.target_component_id or job.payload_json["component_id"]
                component_lock_stmt = select(WorkspaceComponent).where(WorkspaceComponent.id == target_comp_id).with_for_update()
                locked_component = await session.scalar(component_lock_stmt)
                if locked_component is None:
                    raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail="组件不存在。")
                comp_service = WorkspaceComponentService(session)
                current_comp = await comp_service.get(target_comp_id, user_id=job.created_by)
                base_ver = job.base_version_no or job.payload_json.get("base_version_no")
                base_draft_hash = job.source_hash or job.payload_json.get("base_draft_hash")
                if base_ver is not None and current_comp.current_version_no != base_ver:
                    raise AppException(
                        status_code=409,
                        code="COMPONENT_CONCURRENT_MODIFIED",
                        detail=f"组件版本已在诊断期间发生变更 (基准版本: {base_ver}，最新版本: {current_comp.current_version_no})，放弃覆盖。",
                    )
                if base_draft_hash and calculate_source_hash(current_comp.content) != base_draft_hash:
                    raise AppException(
                        status_code=409,
                        code="COMPONENT_CONCURRENT_MODIFIED",
                        detail="组件草稿已在诊断期间发生变更，放弃覆盖。",
                    )

                comp_update_req = WorkspaceComponentUpdateRequest(
                    content=plan_result.prepared_content,
                )
                updated_comp = await comp_service.update(
                    component_id=target_comp_id,
                    payload=comp_update_req,
                    operator_id=job.created_by,
                    commit=False,
                )
                target_id = updated_comp.id
                result_dict = {"component_id": updated_comp.id, "version_no": updated_comp.current_version_no}
            elif job.job_type == "component_metadata":
                target_comp_id = plan_result.target_component_id or job.payload_json["component_id"]
                component_lock_stmt = select(WorkspaceComponent).where(WorkspaceComponent.id == target_comp_id).with_for_update()
                locked_component = await session.scalar(component_lock_stmt)
                if locked_component is None:
                    raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail="组件不存在。")
                comp_service = WorkspaceComponentService(session)
                current_comp = await comp_service.get(target_comp_id, user_id=job.created_by)
                base_ver = job.base_version_no or job.payload_json.get("base_version_no")
                base_draft_hash = job.source_hash or job.payload_json.get("base_draft_hash")
                if base_ver is not None and current_comp.current_version_no != base_ver:
                    raise AppException(
                        status_code=409,
                        code="COMPONENT_CONCURRENT_MODIFIED",
                        detail="组件发布版本已在诊断期间发生变更，放弃覆盖。",
                    )
                if base_draft_hash and calculate_source_hash(current_comp.content) != base_draft_hash:
                    raise AppException(
                        status_code=409,
                        code="COMPONENT_CONCURRENT_MODIFIED",
                        detail="组件草稿已在诊断期间发生变更，放弃覆盖。",
                    )
                updated_comp = await comp_service.update(
                    component_id=target_comp_id,
                    payload=WorkspaceComponentUpdateRequest(
                        name=plan_result.name,
                        import_name=plan_result.import_name,
                        component_type=plan_result.component_type,
                        summary=plan_result.summary,
                        preview_schema=plan_result.preview_schema,
                        change_note=plan_result.change_note,
                    ),
                    operator_id=job.created_by,
                    commit=False,
                )
                target_id = updated_comp.id
                result_dict = {
                    "component_id": updated_comp.id,
                    "version_no": updated_comp.current_version_no,
                }

            # 3. 标记任务成功
            job.status = "succeeded"
            job.target_id = target_id
            job.result_json = result_dict
            job.finished_at = now

            await session.commit()
            logger.info("Mutation 任务执行成功 (ID: %s, target_id: %s)", job_id, target_id)

    async def _handle_job_failure(self, job_id: int, generation: int, error: AppException) -> None:
        """处理任务失败：可重试错误递增 attempt 并退避；确定性错误写为 failed。"""

        now = utc_now()
        session_factory = get_session_factory()
        is_retryable = error.code in RETRYABLE_ERROR_CODES

        async with session_factory() as session:
            stmt = (
                select(ApiMutationJob)
                .where(ApiMutationJob.id == job_id)
                .where(ApiMutationJob.status == "running")
                .where(ApiMutationJob.worker_id == self.worker_id)
                .where(ApiMutationJob.lease_generation == generation)
                .where(ApiMutationJob.lease_expires_at > now)
                .with_for_update()
            )
            job = await session.scalar(stmt)
            if job is None:
                logger.error("Mutation 失败处理 CAS 围栏失效 (ID: %s)", job_id)
                return

            if job.cancel_requested_at is not None:
                job.status = "canceled"
                job.finished_at = now
                await session.commit()
                return

            err_dict = {
                "code": error.code,
                "message": error.detail,
                "retryable": is_retryable,
                "details": getattr(error, "data", None),
            }

            if is_retryable and job.attempt_count + 1 < job.max_attempts:
                # 指数退避重试 (5s, 10s, 20s)
                backoff_seconds = 5 * (2 ** job.attempt_count)
                job.status = "pending"
                job.worker_id = None
                job.lease_expires_at = None
                job.attempt_count += 1
                job.next_attempt_at = now + timedelta(seconds=backoff_seconds)
                job.last_error_code = error.code
                job.error_json = err_dict
                logger.info("Mutation 任务已调度重试 (ID: %s, attempt: %s, delay: %ss)", job_id, job.attempt_count, backoff_seconds)
            else:
                job.status = "failed"
                job.finished_at = now
                job.last_error_code = error.code
                job.error_json = err_dict
                logger.warning("Mutation 任务终态失败 (ID: %s, code: %s)", job_id, error.code)

            await session.commit()

    # ------------------ Sweeper & Recovery ------------------

    @classmethod
    async def recover_expired_running_jobs(cls) -> int:
        """周期性回收租约超时的孤儿 running 任务。"""

        now = utc_now()
        session_factory = get_session_factory()
        recovered_count = 0

        async with session_factory() as session:
            stmt = (
                select(
                    ApiMutationJob.id,
                    ApiMutationJob.lease_generation,
                    ApiMutationJob.attempt_count,
                    ApiMutationJob.max_attempts,
                )
                .where(ApiMutationJob.status == "running")
                .where(ApiMutationJob.lease_expires_at <= now)
            )
            candidates = (await session.execute(stmt)).all()
            for cand_id, cand_gen, attempt_count, max_attempts in candidates:
                if (attempt_count or 0) + 1 < (max_attempts or 3):
                    update_stmt = (
                        update(ApiMutationJob)
                        .where(ApiMutationJob.id == cand_id)
                        .where(ApiMutationJob.status == "running")
                        .where(ApiMutationJob.lease_generation == cand_gen)
                        .values(
                            status="pending",
                            worker_id=None,
                            lease_expires_at=None,
                            lease_generation=(cand_gen or 0) + 1,
                            attempt_count=(attempt_count or 0) + 1,
                            next_attempt_at=now + timedelta(seconds=5),
                            last_error_code="LEASE_TIMEOUT_RECOVERED",
                        )
                    )
                else:
                    update_stmt = (
                        update(ApiMutationJob)
                        .where(ApiMutationJob.id == cand_id)
                        .where(ApiMutationJob.status == "running")
                        .where(ApiMutationJob.lease_generation == cand_gen)
                        .values(
                            status="failed",
                            finished_at=now,
                            last_error_code="LEASE_TIMEOUT_MAX_ATTEMPTS",
                            error_json={
                                "code": "LEASE_TIMEOUT_MAX_ATTEMPTS",
                                "message": "任务执行租约多次超时且已达最大重试次数。",
                                "retryable": False,
                            },
                        )
                    )
                res = await session.execute(update_stmt)
                if res.rowcount > 0:
                    recovered_count += 1

            if recovered_count > 0:
                await session.commit()
                logger.info("已回收 %s 个超时 Mutation 孤儿任务。", recovered_count)

        return recovered_count


async def run_api_mutation_worker_loop(session_factory: Callable[..., AsyncSession]) -> None:
    """生命周期常驻：拉取并执行 ApiMutationJob。"""

    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    logger.info("ApiMutationJob Worker 循环启动 (worker_id: %s)", worker_id)
    while True:
        try:
            async with session_factory() as session:
                service = MutationJobService(session, worker_id=worker_id)
                job = await service.claim_next_pending_job()
            if job is not None:
                await service.execute_job_with_lease(job)
            else:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("ApiMutationJob Worker 循环已取消")
            break
        except Exception as exc:
            logger.warning("ApiMutationJob Worker 循环异常: %s", exc)
            await asyncio.sleep(2.0)


async def run_api_mutation_sweeper_loop(session_factory: Callable[..., AsyncSession]) -> None:
    """生命周期常驻：定期回收租约超时的孤儿 running 任务。"""

    logger.info("ApiMutationJob Sweeper 循环启动")
    while True:
        try:
            await asyncio.sleep(get_settings().mutation_job_recovery_interval_seconds)
            await MutationJobService.recover_expired_running_jobs()
        except asyncio.CancelledError:
            logger.info("ApiMutationJob Sweeper 循环已取消")
            break
        except Exception as exc:
            logger.warning("ApiMutationJob Sweeper 循环异常: %s", exc)
            await asyncio.sleep(5.0)
