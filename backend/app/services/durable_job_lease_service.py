"""文件功能：提供数据库持久化任务的原子认领、租约续期、拥有者流转和过期恢复能力。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import socket
from typing import Any
import uuid

from sqlalchemy import Select, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now

_SQLITE_BUSY_ERROR_CODE = 5
_SQLITE_LOCKED_ERROR_CODE = 6
_SQLITE_LOCK_MESSAGES = ("database is locked", "database table is locked")


@dataclass(frozen=True, slots=True)
class DurableJobRecoverySummary:
    """汇总一次过期租约恢复结果，便于调用方记录结构化日志。"""

    requeued_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0

    @property
    def total_count(self) -> int:
        """返回本次发生状态迁移的任务总数。"""

        return self.requeued_count + self.failed_count + self.cancelled_count


def build_durable_worker_id() -> str:
    """构造跨进程唯一的持久化任务 Worker 标识。"""

    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"


def is_sqlite_lock_error(session: AsyncSession, exc: OperationalError) -> bool:
    """判断当前会话的异常是否为 SQLite BUSY/LOCKED，供持久化任务执行短退避。"""

    if session.get_bind().dialect.name != "sqlite":
        return False
    original_error = exc.orig
    sqlite_error_code = getattr(original_error, "sqlite_errorcode", None)
    if isinstance(sqlite_error_code, int) and sqlite_error_code & 0xFF in {
        _SQLITE_BUSY_ERROR_CODE,
        _SQLITE_LOCKED_ERROR_CODE,
    }:
        return True
    message = str(original_error).lower()
    return any(fragment in message for fragment in _SQLITE_LOCK_MESSAGES)


async def claim_pending_jobs(
    session: AsyncSession,
    model: type[Any],
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    now: datetime | None = None,
    candidate_query: Select[Any] | None = None,
) -> list[int]:
    """以条件 UPDATE 原子认领 pending 任务，返回当前执行者实际取得的任务 ID。"""

    claimed_at = now or utc_now()
    lease_expires_at = claimed_at + timedelta(seconds=max(1, lease_seconds))
    query = candidate_query
    if query is None:
        query = (
            select(model.id)
            .where(model.status == "pending", model.cancel_requested_at.is_(None))
            .order_by(model.created_at.asc(), model.id.asc())
        )
    candidate_ids = list((await session.execute(query.limit(max(1, limit)))).scalars().all())
    # 候选读取不应维持 SQLite 读事务，否则并发认领时可能升级写锁失败。
    await session.commit()

    claimed_ids: list[int] = []
    for job_id in candidate_ids:
        result = await session.execute(
            update(model)
            .where(
                model.id == job_id,
                model.status == "pending",
                model.cancel_requested_at.is_(None),
            )
            .values(
                status="running",
                worker_id=worker_id,
                lease_expires_at=lease_expires_at,
                heartbeat_at=claimed_at,
                attempt_count=model.attempt_count + 1,
                error_code=None,
                error_message=None,
                started_at=claimed_at,
                finished_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        if (result.rowcount or 0) == 1:
            claimed_ids.append(int(job_id))
    await session.commit()
    return claimed_ids


async def renew_running_job_lease(
    session: AsyncSession,
    model: type[Any],
    *,
    job_id: int,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> bool:
    """仅允许当前未过期租约的拥有者续租，避免旧 Worker 重新激活失效任务。"""

    heartbeat_at = now or utc_now()
    result = await session.execute(
        update(model)
        .where(
            model.id == job_id,
            model.status == "running",
            model.worker_id == worker_id,
            model.lease_expires_at.is_not(None),
            model.lease_expires_at > heartbeat_at,
        )
        .values(
            heartbeat_at=heartbeat_at,
            lease_expires_at=heartbeat_at + timedelta(seconds=max(1, lease_seconds)),
        )
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return (result.rowcount or 0) == 1


async def transition_owned_running_job(
    session: AsyncSession,
    model: type[Any],
    *,
    job_id: int,
    worker_id: str,
    values: dict[str, Any],
    require_not_cancelled: bool = False,
    require_active_lease: bool = False,
    commit: bool = True,
) -> bool:
    """按任务 ID、拥有者和可选未过期租约迁移 running 任务，避免旧 Worker 覆盖新状态。"""

    conditions = [model.id == job_id, model.status == "running", model.worker_id == worker_id]
    if require_not_cancelled:
        conditions.append(model.cancel_requested_at.is_(None))
    if require_active_lease:
        conditions.extend([model.lease_expires_at.is_not(None), model.lease_expires_at > utc_now()])
    result = await session.execute(
        update(model)
        .where(*conditions)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if commit:
        await session.commit()
    return (result.rowcount or 0) == 1


async def request_job_cancellation(
    session: AsyncSession,
    model: type[Any],
    *,
    job_id: int,
    now: datetime | None = None,
) -> bool:
    """请求取消任务；pending 立即终止，running 由执行者在安全边界确认。"""

    requested_at = now or utc_now()
    pending_result = await session.execute(
        update(model)
        .where(model.id == job_id, model.status == "pending")
        .values(
            status="cancelled",
            cancel_requested_at=requested_at,
            finished_at=requested_at,
            worker_id=None,
            lease_expires_at=None,
            heartbeat_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    running_result = await session.execute(
        update(model)
        .where(model.id == job_id, model.status == "running", model.cancel_requested_at.is_(None))
        .values(cancel_requested_at=requested_at)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return (pending_result.rowcount or 0) + (running_result.rowcount or 0) > 0


async def recover_expired_running_jobs(
    session: AsyncSession,
    model: type[Any],
    *,
    max_attempts: int,
    interrupted_error_code: str,
    interrupted_error_message: str,
    now: datetime | None = None,
) -> DurableJobRecoverySummary:
    """只恢复租约为空或已经过期的 running 任务，并在空队列时避免发起写 DML。"""

    recovered_at = now or utc_now()
    expired = (model.lease_expires_at.is_(None)) | (model.lease_expires_at <= recovered_at)
    base_conditions = (model.status == "running", expired)

    # 定时恢复在空闲期会频繁执行。先只读筛选，避免 SQLite 因无命中 UPDATE
    # 反复争抢 writer 锁；后续 UPDATE 仍带过期条件以抵御筛选后的并发变化。
    candidates = list(
        (
            await session.execute(
                select(model.id, model.cancel_requested_at, model.attempt_count).where(*base_conditions)
            )
        ).all()
    )
    if not candidates:
        # 只结束本次只读事务，不发送任何 UPDATE。
        await session.commit()
        return DurableJobRecoverySummary()

    attempt_limit = max(1, max_attempts)
    cancelled_ids = [int(row.id) for row in candidates if row.cancel_requested_at is not None]
    requeued_ids = [
        int(row.id)
        for row in candidates
        if row.cancel_requested_at is None and int(row.attempt_count) < attempt_limit
    ]
    failed_ids = [
        int(row.id)
        for row in candidates
        if row.cancel_requested_at is None and int(row.attempt_count) >= attempt_limit
    ]
    cancelled_count = 0
    requeued_count = 0
    failed_count = 0
    if cancelled_ids:
        cancelled = await session.execute(
            update(model)
            .where(*base_conditions, model.id.in_(cancelled_ids), model.cancel_requested_at.is_not(None))
            .values(
                status="cancelled",
                finished_at=recovered_at,
                lease_expires_at=None,
                heartbeat_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        cancelled_count = int(cancelled.rowcount or 0)
    if requeued_ids:
        requeued = await session.execute(
            update(model)
            .where(
                *base_conditions,
                model.id.in_(requeued_ids),
                model.cancel_requested_at.is_(None),
                model.attempt_count < attempt_limit,
            )
            .values(
                status="pending",
                worker_id=None,
                lease_expires_at=None,
                heartbeat_at=None,
                error_code=None,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        requeued_count = int(requeued.rowcount or 0)
    if failed_ids:
        failed = await session.execute(
            update(model)
            .where(
                *base_conditions,
                model.id.in_(failed_ids),
                model.cancel_requested_at.is_(None),
                model.attempt_count >= attempt_limit,
            )
            .values(
                status="failed",
                lease_expires_at=None,
                heartbeat_at=None,
                error_code=interrupted_error_code,
                error_message=interrupted_error_message,
                finished_at=recovered_at,
            )
            .execution_options(synchronize_session=False)
        )
        failed_count = int(failed.rowcount or 0)
    await session.commit()
    return DurableJobRecoverySummary(
        requeued_count=requeued_count,
        failed_count=failed_count,
        cancelled_count=cancelled_count,
    )
