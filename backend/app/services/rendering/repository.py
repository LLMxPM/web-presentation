"""文件功能：远程渲染请求、尝试、Worker、调度与结果的数据库仓储。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.models.render_attempt import RenderAttempt
from app.models.render_execution import RenderResult, RenderSchedulerState, RenderWorker
from app.models.render_request import RenderRequest
from render_contracts.constants import (
    ATTEMPT_OCCUPYING_STATUSES,
    ATTEMPT_STATUS_RESERVED,
    ATTEMPT_STATUS_TERMINAL,
    ATTEMPT_STATUS_UNKNOWN,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_EXECUTING,
    REQUEST_STATUS_EXPIRED,
    REQUEST_STATUS_FAILED,
    REQUEST_STATUS_QUEUED,
    REQUEST_STATUS_RETRY_WAIT,
    REQUEST_TERMINAL_STATUSES,
    SCHEDULE_CATEGORY_BACKGROUND,
    SCHEDULE_CATEGORY_INTERACTIVE,
    SCHEDULE_CATEGORY_WEIGHT_BACKGROUND,
    SCHEDULE_CATEGORY_WEIGHT_INTERACTIVE,
)
from render_contracts.errors import (
    ERROR_CODE_CANCELLED,
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_RESULT_LOST,
)


class RenderRepository:
    """渲染控制面持久化仓储，所有终态与配额释放使用条件更新。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_scheduler_state(self) -> RenderSchedulerState:
        """读取或初始化全局调度状态单行。"""

        state = await self.session.scalar(
            select(RenderSchedulerState).where(RenderSchedulerState.singleton_key == "global")
        )
        if state is None:
            state = RenderSchedulerState(singleton_key="global")
            self.session.add(state)
            await self.session.flush()
        return state

    async def lock_scheduler_state_for_queue_admission(self) -> RenderSchedulerState:
        """写锁定调度状态，串行化队列容量检查与请求插入。"""

        state = await self.get_scheduler_state()
        # UPDATE 在 PostgreSQL 中锁住单行，在 SQLite 中提前取得写事务，
        # 使 queue_size/workspace_queue 与后续 INSERT 不再存在检查竞态。
        state.version = int(state.version or 0) + 1
        await self.session.flush()
        return state

    async def count_active_attempts(self, *, workspace_id: int | None = None) -> int:
        """统计未确认释放的 attempt 占用。"""

        stmt = select(func.count()).select_from(RenderAttempt).where(
            RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
            RenderAttempt.active_occupancy == 1,
        )
        if workspace_id is not None:
            stmt = stmt.where(RenderAttempt.request_id.in_(
                select(RenderRequest.id).where(RenderRequest.workspace_id == workspace_id)
            ))
        return int(await self.session.scalar(stmt) or 0)

    async def count_queued_requests(self, *, workspace_id: int | None = None) -> int:
        """统计待处理请求队列长度。"""

        statuses = (REQUEST_STATUS_QUEUED, REQUEST_STATUS_RETRY_WAIT)
        stmt = select(func.count()).select_from(RenderRequest).where(RenderRequest.status.in_(statuses))
        if workspace_id is not None:
            stmt = stmt.where(RenderRequest.workspace_id == workspace_id)
        return int(await self.session.scalar(stmt) or 0)

    async def list_idle_workers(self) -> list[RenderWorker]:
        """列出未隔离且槽位空闲的当前可派发 Worker；每个 worker_id 只取最新 epoch。"""

        result = await self.session.scalars(
            select(RenderWorker)
            .where(RenderWorker.isolated.is_(False))
            .where(RenderWorker.slot_state == "idle")
            .where(RenderWorker.status == "ready")
            .order_by(
                RenderWorker.worker_id.asc(),
                RenderWorker.last_heartbeat_at.desc().nullslast(),
                RenderWorker.id.desc(),
            )
        )
        latest_by_worker: dict[str, RenderWorker] = {}
        for worker in result.all():
            current = latest_by_worker.get(worker.worker_id)
            if current is None:
                latest_by_worker[worker.worker_id] = worker
                continue
            current_key = (current.last_heartbeat_at or current.registered_at, current.id)
            candidate_key = (worker.last_heartbeat_at or worker.registered_at, worker.id)
            if candidate_key > current_key:
                latest_by_worker[worker.worker_id] = worker
        return list(latest_by_worker.values())

    async def ensure_workers_from_config(self, endpoints: list[dict[str, str]], *, profile_digest: str) -> list[RenderWorker]:
        """根据受信部署配置登记 Worker 地址。"""

        workers: list[RenderWorker] = []
        for item in endpoints:
            worker_id = item["worker_id"]
            base_url = item["base_url"]
            worker = await self.session.scalar(
                select(RenderWorker)
                .where(RenderWorker.worker_id == worker_id)
                .order_by(RenderWorker.registered_at.desc())
                .limit(1)
            )
            if worker is None or worker.service_base_url != base_url:
                worker = RenderWorker(
                    worker_id=worker_id,
                    worker_epoch="pending",
                    service_base_url=base_url,
                    status="registered",
                    isolated=False,
                    render_profile_digest=profile_digest,
                    slot_state="idle",
                    slot_generation=0,
                    registered_at=utc_now(),
                )
                self.session.add(worker)
                await self.session.flush()
            workers.append(worker)
        return workers

    async def upsert_worker_heartbeat(
        self,
        *,
        worker_id: str,
        worker_epoch: str,
        service_base_url: str,
        render_profile_digest: str,
        environment_summary: dict[str, Any],
        slot_state: str,
        slot_generation: int,
    ) -> RenderWorker:
        """记录 Worker 心跳与当前 epoch；新 epoch 不自动抹掉旧占用。"""

        worker = await self.session.scalar(
            select(RenderWorker)
            .where(RenderWorker.worker_id == worker_id, RenderWorker.worker_epoch == worker_epoch)
        )
        if worker is None:
            worker = RenderWorker(
                worker_id=worker_id,
                worker_epoch=worker_epoch,
                service_base_url=service_base_url,
                status="ready",
                isolated=False,
                render_profile_digest=render_profile_digest,
                environment_summary=environment_summary,
                slot_state=slot_state,
                slot_generation=slot_generation,
                registered_at=utc_now(),
                last_heartbeat_at=utc_now(),
            )
            self.session.add(worker)
        else:
            # 已有占用中的 attempt 时不把槽位冲回 idle，避免双派。
            has_active = await self.request_has_unreleased_attempt_for_worker(
                worker_id=worker_id,
                worker_epoch=worker_epoch,
            )
            worker.service_base_url = service_base_url
            worker.status = "ready"
            worker.render_profile_digest = render_profile_digest
            worker.environment_summary = environment_summary
            if not has_active:
                # 没有 DB attempt 时仍须保留 Renderer 报告的 busy，避免错误双派。
                worker.slot_state = slot_state if slot_state in {"idle", "busy"} else "unknown"
            worker.slot_generation = slot_generation if not has_active else worker.slot_generation
            worker.last_heartbeat_at = utc_now()
        await self._isolate_stale_worker_epochs(worker_id=worker_id, keep_epoch=worker_epoch)
        await self.session.flush()
        return worker

    async def _isolate_stale_worker_epochs(self, *, worker_id: str, keep_epoch: str) -> None:
        """隔离同 worker_id 的其它 epoch，避免陈旧 idle 行被再次派发。"""

        stale_rows = list(
            (
                await self.session.scalars(
                    select(RenderWorker).where(
                        RenderWorker.worker_id == worker_id,
                        RenderWorker.worker_epoch != keep_epoch,
                        RenderWorker.isolated.is_(False),
                    )
                )
            ).all()
        )
        for row in stale_rows:
            row.isolated = True
            row.isolation_reason = "stale_worker_epoch"
            row.status = "retired"

    async def request_has_unreleased_attempt_for_worker(
        self,
        *,
        worker_id: str,
        worker_epoch: str,
    ) -> bool:
        """判断指定 Worker/epoch 是否仍有未释放占用。"""

        stmt = select(func.count()).select_from(RenderAttempt).where(
            RenderAttempt.worker_id == worker_id,
            RenderAttempt.worker_epoch == worker_epoch,
            RenderAttempt.active_occupancy == 1,
            RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
        )
        return int(await self.session.scalar(stmt) or 0) > 0

    async def select_dispatch_candidate(
        self,
        *,
        prefer_category: str,
        exclude_request_ids: set[int] | None = None,
    ) -> RenderRequest | None:
        """按类别轮转选择可派发请求；同类别内按 workspace 轮转再按入队顺序。"""

        now = utc_now()
        statuses = [REQUEST_STATUS_QUEUED, REQUEST_STATUS_RETRY_WAIT]
        base = (
            select(RenderRequest)
            .where(RenderRequest.status.in_(statuses))
            .where(RenderRequest.deadline_at > now)
            .where(RenderRequest.cancel_requested.is_(False))
            .where(or_(RenderRequest.retry_after.is_(None), RenderRequest.retry_after <= now))
            .where(RenderRequest.attempt_count < RenderRequest.max_attempts)
        )
        if exclude_request_ids:
            base = base.where(RenderRequest.id.notin_(exclude_request_ids))

        state = await self.get_scheduler_state()
        cursor_ws = state.cursor_workspace_id

        async def _pick(category: str) -> RenderRequest | None:
            """在类别内优先非游标 workspace 轮转，避免单工作空间饿死其它空间。"""

            stmt = base.where(RenderRequest.schedule_category == category)
            if cursor_ws is not None:
                # False(非游标) 排在 True(游标) 之前，实现真正轮转。
                stmt = stmt.order_by(
                    (RenderRequest.workspace_id == cursor_ws).asc(),
                    (RenderRequest.workspace_id > cursor_ws).desc(),
                    RenderRequest.workspace_id.asc(),
                    RenderRequest.created_at.asc(),
                    RenderRequest.id.asc(),
                )
            else:
                stmt = stmt.order_by(
                    RenderRequest.workspace_id.asc(),
                    RenderRequest.created_at.asc(),
                    RenderRequest.id.asc(),
                )
            candidate = await self.session.scalar(stmt.limit(1))
            if candidate is not None:
                return candidate
            # 游标 workspace 无可派发时，再按全局入队顺序取一条。
            stmt_fallback = (
                base.where(RenderRequest.schedule_category == category).order_by(
                    RenderRequest.created_at.asc(),
                    RenderRequest.id.asc(),
                )
            )
            return await self.session.scalar(stmt_fallback.limit(1))

        candidate = await _pick(prefer_category)
        if candidate is not None:
            return candidate
        other = (
            SCHEDULE_CATEGORY_BACKGROUND
            if prefer_category == SCHEDULE_CATEGORY_INTERACTIVE
            else SCHEDULE_CATEGORY_INTERACTIVE
        )
        return await _pick(other)

    async def advance_scheduler_cursor(self, *, workspace_id: int | None, request_id: int | None) -> None:
        """推进共享调度游标，供多 Backend 公平轮转。"""

        state = await self.get_scheduler_state()
        if workspace_id is not None:
            state.cursor_workspace_id = int(workspace_id)
        if request_id is not None:
            state.cursor_request_id = int(request_id)
        state.version = int(state.version or 0) + 1
        await self.session.flush()

    async def flip_scheduler_category(self) -> str:
        """按交互 3 : 后台 1 在共享状态上推进类别游标。"""

        state = await self.get_scheduler_state()
        current = str(state.cursor_category or SCHEDULE_CATEGORY_INTERACTIVE)
        weights = self.category_weights()
        # 简化轮转：连续派发达到交互权重后切到后台一次。
        counter = int(state.workspace_weights.get("_category_counter") or 0) if isinstance(state.workspace_weights, dict) else 0
        counter += 1
        if current == SCHEDULE_CATEGORY_INTERACTIVE and counter >= weights[SCHEDULE_CATEGORY_INTERACTIVE]:
            counter = 0
            current = SCHEDULE_CATEGORY_BACKGROUND
        elif current == SCHEDULE_CATEGORY_BACKGROUND:
            counter = 0
            current = SCHEDULE_CATEGORY_INTERACTIVE
        payload = dict(state.workspace_weights or {}) if isinstance(state.workspace_weights, dict) else {}
        payload["_category_counter"] = counter
        state.workspace_weights = payload
        state.cursor_category = current
        state.version = int(state.version or 0) + 1
        await self.session.flush()
        return current

    async def reserve_attempt(
        self,
        *,
        request: RenderRequest,
        worker: RenderWorker,
        request_digest: str,
    ) -> RenderAttempt:
        """在已锁定 Worker 槽位上创建 reserved attempt，并写入占用租约。"""

        now = utc_now()
        settings = get_settings()
        attempt_no = int(request.attempt_count) + 1
        # 条件占用请求，防止多 Backend 双派同一逻辑请求。
        claim_result = await self.session.execute(
            update(RenderRequest)
            .where(
                RenderRequest.id == request.id,
                RenderRequest.status.in_((REQUEST_STATUS_QUEUED, REQUEST_STATUS_RETRY_WAIT)),
                RenderRequest.attempt_count == attempt_no - 1,
            )
            .values(
                status="executing",
                attempt_count=attempt_no,
                started_at=now if request.started_at is None else request.started_at,
            )
        )
        if not claim_result.rowcount:
            raise RuntimeError("渲染请求已被其它调度方认领")
        request.status = "executing"
        request.attempt_count = attempt_no
        if request.started_at is None:
            request.started_at = now
        next_slot_generation = int(worker.slot_generation) + 1
        # 只在 attempt 上预约「接管后」generation，不在 reserve 时推进 Worker 代次。
        # Renderer 仅在真正 accept 后提交 generation；未接管释放时双方保持一致。
        worker.slot_state = "busy"
        lease_expires = now + timedelta(seconds=float(settings.render_attempt_lease_seconds))
        attempt = RenderAttempt(
            attempt_uid=str(uuid.uuid4()),
            request_id=request.id,
            attempt_no=attempt_no,
            worker_id=worker.worker_id,
            worker_epoch=worker.worker_epoch,
            slot_generation=next_slot_generation,
            status=ATTEMPT_STATUS_RESERVED,
            cleanup_status="pending",
            active_occupancy=1,
            request_digest=request_digest,
            reserved_at=now,
            lease_expires_at=lease_expires,
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def mark_attempt_dispatched(self, attempt_id: int, *, worker_id: str, worker_epoch: str) -> bool:
        """条件更新 reserved→dispatched；失败则执行者不得继续发送。"""

        settings = get_settings()
        result = await self.session.execute(
            update(RenderAttempt)
            .where(
                RenderAttempt.id == attempt_id,
                RenderAttempt.status == ATTEMPT_STATUS_RESERVED,
                RenderAttempt.worker_id == worker_id,
                RenderAttempt.worker_epoch == worker_epoch,
                RenderAttempt.active_occupancy == 1,
            )
            .values(
                status="dispatched",
                dispatched_at=utc_now(),
                lease_expires_at=utc_now() + timedelta(seconds=float(settings.render_attempt_lease_seconds)),
            )
        )
        return bool(result.rowcount and int(result.rowcount) > 0)

    async def mark_attempt_accepted(
        self,
        attempt_id: int,
        *,
        request_digest: str | None = None,
    ) -> bool:
        """条件更新 dispatched→accepted；禁止把终态 attempt 复活为占用态。

        成功接管后才推进 Worker slot_generation，与 Renderer accept 提交语义对齐。
        """

        settings = get_settings()
        values: dict[str, Any] = {
            "status": "accepted",
            "accepted_at": utc_now(),
            "lease_expires_at": utc_now() + timedelta(seconds=float(settings.render_attempt_lease_seconds)),
        }
        if request_digest:
            values["request_digest"] = request_digest
        result = await self.session.execute(
            update(RenderAttempt)
            .where(
                RenderAttempt.id == attempt_id,
                RenderAttempt.status.in_(("dispatched", "accepted", "running")),
                RenderAttempt.active_occupancy == 1,
            )
            .values(**values)
        )
        if not (result.rowcount and int(result.rowcount) > 0):
            return False
        attempt = await self.get_attempt(attempt_id)
        if attempt is not None:
            worker = await self._get_worker(attempt.worker_id, attempt.worker_epoch)
            if worker is not None and int(attempt.slot_generation) > int(worker.slot_generation or 0):
                worker.slot_generation = int(attempt.slot_generation)
        return True

    async def extend_attempt_lease(self, attempt_id: int) -> None:
        """延长占用租约，供仍在运行的 attempt 保活。"""

        settings = get_settings()
        await self.session.execute(
            update(RenderAttempt)
            .where(
                RenderAttempt.id == attempt_id,
                RenderAttempt.active_occupancy == 1,
                RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
            )
            .values(
                lease_expires_at=utc_now() + timedelta(seconds=float(settings.render_attempt_lease_seconds))
            )
        )

    async def release_expired_attempt_leases(self, *, limit: int = 20) -> int:
        """收敛租约过期的占用 attempt，避免容量永久泄漏。"""

        now = utc_now()
        rows = list(
            (
                await self.session.execute(
                    select(
                        RenderAttempt.id,
                        RenderAttempt.request_id,
                        RenderAttempt.worker_id,
                        RenderAttempt.worker_epoch,
                    )
                    .where(RenderAttempt.active_occupancy == 1)
                    .where(RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)))
                    .where(
                        or_(
                            RenderAttempt.lease_expires_at.is_(None),
                            RenderAttempt.lease_expires_at <= now,
                        )
                    )
                    .limit(limit)
                )
            ).all()
        )
        released = 0
        for attempt_id, request_id, worker_id, worker_epoch in rows:
            result = await self.session.execute(
                update(RenderAttempt)
                .where(
                    RenderAttempt.id == attempt_id,
                    RenderAttempt.active_occupancy == 1,
                    RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
                )
                .values(
                    status=ATTEMPT_STATUS_TERMINAL,
                    cleanup_status="released",
                    active_occupancy=0,
                    finished_at=now,
                    cleaned_at=now,
                    error_code="RENDER_DEADLINE_EXCEEDED",
                    error_message="attempt 占用租约超时，已由协调器收敛释放。",
                )
            )
            if not result.rowcount:
                continue
            released += 1
            await self._recover_request_after_expired_attempt(request_id=int(request_id), now=now)
            worker = await self._get_worker(worker_id, worker_epoch)
            if worker is not None:
                still_occupied = await self.request_has_unreleased_attempt_for_worker(
                    worker_id=worker_id,
                    worker_epoch=worker_epoch,
                )
                if not still_occupied:
                    worker.slot_state = "idle"
        return released

    async def _recover_request_after_expired_attempt(self, *, request_id: int, now: datetime) -> None:
        """释放过期 attempt 后同步推进父请求，避免 request 永久停留 executing。"""

        request = await self.get_request(request_id)
        if request is None or request.status != REQUEST_STATUS_EXECUTING:
            return

        if request.cancel_requested:
            status = REQUEST_STATUS_CANCELLED
            error_code = ERROR_CODE_CANCELLED
            error_message = "渲染请求已取消，过期 attempt 已收敛。"
            finished_at = now
            retry_after = None
        elif request.deadline_at <= now:
            status = REQUEST_STATUS_EXPIRED
            error_code = ERROR_CODE_DEADLINE_EXCEEDED
            error_message = "渲染请求在 attempt 租约收敛时已超过总预算期限。"
            finished_at = now
            retry_after = None
        elif request.attempt_count >= request.max_attempts:
            status = REQUEST_STATUS_FAILED
            error_code = ERROR_CODE_RESULT_LOST
            error_message = "Renderer attempt 租约超时且已达到最大重试次数。"
            finished_at = now
            retry_after = None
        else:
            status = REQUEST_STATUS_RETRY_WAIT
            error_code = ERROR_CODE_RESULT_LOST
            error_message = "Renderer attempt 租约超时，结果未知，已安排重试。"
            finished_at = None
            retry_after = now + timedelta(seconds=2)

        result = await self.session.execute(
            update(RenderRequest)
            .where(
                RenderRequest.id == request.id,
                RenderRequest.status == REQUEST_STATUS_EXECUTING,
            )
            .values(
                status=status,
                retry_after=retry_after,
                error_code=error_code,
                error_message=error_message,
                finished_at=finished_at,
            )
        )
        if result.rowcount:
            request.status = status
            request.retry_after = retry_after
            request.error_code = error_code
            request.error_message = error_message
            request.finished_at = finished_at

    async def mark_attempt_not_taken(self, attempt_id: int, *, error_code: str) -> bool:
        """明确未接管的拒绝：结束 attempt 并释放占位。"""

        now = utc_now()
        attempt = await self.session.get(RenderAttempt, attempt_id)
        if attempt is None or attempt.status not in {"reserved", "dispatched"}:
            return False
        if attempt.status == "dispatched":
            # 已派发但 Worker 明确未接管时，也允许释放。
            pass
        attempt.status = ATTEMPT_STATUS_TERMINAL
        attempt.cleanup_status = "released"
        attempt.active_occupancy = 0
        attempt.dispatch_error_code = error_code
        attempt.error_code = error_code
        attempt.finished_at = now
        attempt.cleaned_at = now
        worker = await self._get_worker(attempt.worker_id, attempt.worker_epoch)
        if worker is not None:
            still_occupied = await self.request_has_unreleased_attempt_for_worker(
                worker_id=attempt.worker_id,
                worker_epoch=attempt.worker_epoch,
            )
            if not still_occupied:
                worker.slot_state = "idle"
        return True

    async def request_has_unreleased_attempt(self, request_id: int) -> bool:
        """判断请求是否存在未确认释放的 attempt。"""

        stmt = select(func.count()).select_from(RenderAttempt).where(
            RenderAttempt.request_id == request_id,
            RenderAttempt.active_occupancy == 1,
            RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
        )
        return int(await self.session.scalar(stmt) or 0) > 0

    async def get_attempt(self, attempt_id: int) -> RenderAttempt | None:
        """按主键读取 attempt。"""

        return await self.session.get(RenderAttempt, attempt_id)

    async def get_attempt_by_uid(self, attempt_uid: str) -> RenderAttempt | None:
        """按外部 attempt UID 读取 attempt。"""

        return await self.session.scalar(select(RenderAttempt).where(RenderAttempt.attempt_uid == attempt_uid))

    async def get_request(self, request_id: int) -> RenderRequest | None:
        """按主键读取渲染请求。"""

        return await self.session.get(RenderRequest, request_id)

    async def get_request_by_key(
        self,
        *,
        logical_owner_key: str,
        business_stage: str,
        operation: str,
        request_key: str,
    ) -> RenderRequest | None:
        """按幂等键读取既有请求。"""

        return await self.session.scalar(
            select(RenderRequest).where(
                RenderRequest.logical_owner_key == logical_owner_key,
                RenderRequest.business_stage == business_stage,
                RenderRequest.operation == operation,
                RenderRequest.request_key == request_key,
            )
        )

    async def save_result(
        self,
        *,
        request: RenderRequest,
        attempt: RenderAttempt,
        payload: dict[str, Any],
        object_refs: dict[str, Any],
        environment_summary: dict[str, Any],
        input_digest: str,
        render_profile_digest: str,
        request_digest: str,
    ) -> RenderResult | None:
        """保存有界结果并条件更新请求终态与槽位释放。"""

        now = utc_now()
        result_obj = RenderResult(
            request_id=request.id,
            attempt_id=attempt.id,
            operation=request.operation,
            input_digest=input_digest,
            render_profile_digest=render_profile_digest,
            request_digest=request_digest,
            environment_summary=environment_summary,
            payload=payload,
            object_refs=object_refs,
            worker_id=attempt.worker_id,
            worker_epoch=attempt.worker_epoch,
        )
        self.session.add(result_obj)
        await self.session.flush()
        # 条件更新：仅占用中的 attempt 可以写入终态，避免并发重复释放。
        occupy_statuses = tuple(ATTEMPT_OCCUPYING_STATUSES)
        update_result = await self.session.execute(
            update(RenderAttempt)
            .where(
                RenderAttempt.id == attempt.id,
                RenderAttempt.active_occupancy == 1,
                RenderAttempt.status.in_(occupy_statuses),
            )
            .values(
                status=ATTEMPT_STATUS_TERMINAL,
                cleanup_status="released",
                active_occupancy=0,
                finished_at=now,
                cleaned_at=now,
            )
        )
        if not update_result.rowcount:
            await self.session.rollback()
            return None
        attempt.status = ATTEMPT_STATUS_TERMINAL
        attempt.cleanup_status = "released"
        attempt.active_occupancy = 0
        attempt.finished_at = now
        attempt.cleaned_at = now
        # 请求终态同样条件更新，避免与 fail_attempt 双写。
        request_update = await self.session.execute(
            update(RenderRequest)
            .where(
                RenderRequest.id == request.id,
                RenderRequest.status.notin_(tuple(REQUEST_TERMINAL_STATUSES)),
            )
            .values(
                status="succeeded",
                result_id=result_obj.id,
                finished_at=now,
                error_code=None,
                error_message=None,
            )
        )
        if request_update.rowcount:
            request.status = "succeeded"
            request.result_id = result_obj.id
            request.finished_at = now
        worker = await self._get_worker(attempt.worker_id, attempt.worker_epoch)
        if worker is not None:
            still_occupied = await self.request_has_unreleased_attempt_for_worker(
                worker_id=attempt.worker_id,
                worker_epoch=attempt.worker_epoch,
            )
            if not still_occupied:
                worker.slot_state = "idle"
        return result_obj

    async def fail_attempt(
        self,
        *,
        request: RenderRequest,
        attempt: RenderAttempt,
        error_code: str,
        error_message: str,
        retryable: bool,
        retry_after: datetime | None,
        release_slot: bool,
        terminal: bool,
    ) -> None:
        """记录 attempt 失败并按策略重排或形成请求终态。

        release_slot=True 时必须真正释放占用；条件更新失败说明已被其它路径
        收敛，此时不得再改写请求状态，避免双写。
        """

        now = utc_now()
        attempt.error_code = error_code
        attempt.error_message = error_message
        occupy_statuses = tuple(ATTEMPT_OCCUPYING_STATUSES)
        released = False
        if release_slot:
            update_result = await self.session.execute(
                update(RenderAttempt)
                .where(
                    RenderAttempt.id == attempt.id,
                    RenderAttempt.active_occupancy == 1,
                    RenderAttempt.status.in_(occupy_statuses),
                )
                .values(
                    status=ATTEMPT_STATUS_TERMINAL,
                    cleanup_status="released",
                    active_occupancy=0,
                    finished_at=now,
                    cleaned_at=now,
                    error_code=error_code,
                    error_message=error_message,
                )
            )
            released = bool(update_result.rowcount)
            if released:
                attempt.status = ATTEMPT_STATUS_TERMINAL
                attempt.cleanup_status = "released"
                attempt.active_occupancy = 0
                attempt.finished_at = now
                attempt.cleaned_at = now
                worker = await self._get_worker(attempt.worker_id, attempt.worker_epoch)
                if worker is not None:
                    still_occupied = await self.request_has_unreleased_attempt_for_worker(
                        worker_id=attempt.worker_id,
                        worker_epoch=attempt.worker_epoch,
                    )
                    if not still_occupied:
                        worker.slot_state = "idle"
            else:
                # 已被其它路径收敛，不再改写请求状态。
                return
        else:
            await self.session.execute(
                update(RenderAttempt)
                .where(
                    RenderAttempt.id == attempt.id,
                    RenderAttempt.active_occupancy == 1,
                    RenderAttempt.status.in_(occupy_statuses),
                )
                .values(
                    status=ATTEMPT_STATUS_UNKNOWN,
                    cleanup_status="pending",
                    error_code=error_code,
                    error_message=error_message,
                    lease_expires_at=now
                    + timedelta(seconds=float(get_settings().render_unknown_reconcile_after_seconds)),
                )
            )
            attempt.status = ATTEMPT_STATUS_UNKNOWN
            attempt.cleanup_status = "pending"

        if terminal or not retryable or request.attempt_count >= request.max_attempts:
            # attempt 级 deadline 默认可重试；仅请求总预算耗尽/达最大次数时收敛为 expired。
            if error_code == ERROR_CODE_CANCELLED:
                final_status = REQUEST_STATUS_CANCELLED
            elif error_code == ERROR_CODE_DEADLINE_EXCEEDED and (
                terminal
                or (request.deadline_at is not None and request.deadline_at <= now)
                or request.attempt_count >= request.max_attempts
            ):
                final_status = REQUEST_STATUS_EXPIRED
            else:
                final_status = REQUEST_STATUS_FAILED
            await self.session.execute(
                update(RenderRequest)
                .where(
                    RenderRequest.id == request.id,
                    RenderRequest.status.notin_(("succeeded",)),
                )
                .values(
                    status=final_status,
                    error_code=error_code,
                    error_message=error_message,
                    finished_at=now,
                )
            )
            if request.status != "succeeded":
                request.status = final_status
                request.error_code = error_code
                request.error_message = error_message
                request.finished_at = now
        elif retryable and request.status not in REQUEST_TERMINAL_STATUSES:
            await self.session.execute(
                update(RenderRequest)
                .where(
                    RenderRequest.id == request.id,
                    RenderRequest.status.notin_(tuple(REQUEST_TERMINAL_STATUSES)),
                )
                .values(
                    status=REQUEST_STATUS_RETRY_WAIT,
                    retry_after=retry_after,
                    error_code=error_code,
                    error_message=error_message,
                )
            )
            if request.status not in REQUEST_TERMINAL_STATUSES:
                request.status = REQUEST_STATUS_RETRY_WAIT
                request.retry_after = retry_after
                request.error_code = error_code
                request.error_message = error_message

    async def cancel_request(self, request_id: int) -> RenderRequest | None:
        """请求取消：无活动 attempt 时可直接终态，否则保留资源核对。"""

        request = await self.get_request(request_id)
        if request is None or request.status in REQUEST_TERMINAL_STATUSES:
            return request
        now = utc_now()
        request.cancel_requested = True
        request.cancel_version += 1
        request.cancel_requested_at = now
        has_active = await self.request_has_unreleased_attempt(request_id)
        if not has_active:
            request.status = "cancelled"
            request.error_code = "RENDER_CANCELLED"
            request.error_message = "渲染请求已取消。"
            request.finished_at = now
        return request

    async def expire_requests(self, *, limit: int = 100) -> int:
        """把超过 deadline 且无活动 attempt 的排队请求标记为过期。"""

        now = utc_now()
        active_request_ids = select(RenderAttempt.request_id).where(
            RenderAttempt.active_occupancy == 1,
            RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)),
        )
        result = await self.session.execute(
            update(RenderRequest)
            .where(
                RenderRequest.status.in_((REQUEST_STATUS_QUEUED, REQUEST_STATUS_RETRY_WAIT)),
                RenderRequest.deadline_at <= now,
                RenderRequest.id.notin_(active_request_ids),
            )
            .values(
                status="expired",
                error_code="RENDER_DEADLINE_EXCEEDED",
                error_message="渲染请求超过总预算期限。",
                finished_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

    async def list_cancelled_active_attempts(self, *, limit: int = 20) -> list[RenderAttempt]:
        """列出已请求取消且仍有占用的 attempt，供协调器下发取消。"""

        return list(
            (
                await self.session.scalars(
                    select(RenderAttempt)
                    .join(RenderRequest, RenderRequest.id == RenderAttempt.request_id)
                    .where(RenderRequest.cancel_requested.is_(True))
                    .where(RenderAttempt.active_occupancy == 1)
                    .where(RenderAttempt.status.in_(tuple(ATTEMPT_OCCUPYING_STATUSES)))
                    .limit(limit)
                )
            ).all()
        )

    async def get_result_for_request(self, request_id: int) -> RenderResult | None:
        """读取请求对应结果。"""

        return await self.session.scalar(
            select(RenderResult).where(RenderResult.request_id == request_id).order_by(RenderResult.id.desc()).limit(1)
        )

    async def mark_result_consumed(self, result_id: int) -> bool:
        """条件标记结果已消费，重复消息不重复更新业务事实。"""

        result = await self.session.get(RenderResult, result_id)
        if result is None or result.consumed_at is not None:
            return False
        result.consumed_at = utc_now()
        return True

    async def _get_worker(self, worker_id: str | None, worker_epoch: str | None) -> RenderWorker | None:
        """按 Worker/epoch 读取节点记录。"""

        if not worker_id or not worker_epoch:
            return None
        return await self.session.scalar(
            select(RenderWorker).where(
                RenderWorker.worker_id == worker_id,
                RenderWorker.worker_epoch == worker_epoch,
            )
        )

    @staticmethod
    def category_weights() -> dict[str, int]:
        """返回调度类别权重（描述派发次数，不宣称 CPU 比例）。"""

        return {
            SCHEDULE_CATEGORY_INTERACTIVE: SCHEDULE_CATEGORY_WEIGHT_INTERACTIVE,
            SCHEDULE_CATEGORY_BACKGROUND: SCHEDULE_CATEGORY_WEIGHT_BACKGROUND,
        }
