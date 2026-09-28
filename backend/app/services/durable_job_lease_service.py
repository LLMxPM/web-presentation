"""文件功能：提供数据库持久化任务的原子认领、租约续期、拥有者流转和过期恢复能力。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import socket
from typing import Any
import uuid

from sqlalchemy import Select, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Update

from app.core.time_utils import utc_now
from app.db.tx import commit_end_read, row_locks_hold_until_commit


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


# 认领时序里最容易被写错的四个环节收在本函数：候选读取的 LIMIT、读事务结束、
# 逐条 CAS 的执行选项与 rowcount 判定、以及末尾一次性提交。
ClaimCasFactory = Callable[[Row[Any]], "Update | None"]


async def claim_rows_by_cas(
    session: AsyncSession,
    model: type[Any],
    *,
    candidate_query: Select[Any],
    candidate_limit: int,
    claim_cas: ClaimCasFactory,
    max_claims: int | None = None,
) -> list[Row[Any]]:
    """按「加锁读候选 → 逐条 CAS → 提交」认领任务，返回成功认领的候选行。

    输入是只选出主键（可附带认领所需的其它列）的候选查询，和把一行候选映射为条件
    UPDATE 的 `claim_cas`；返回该行为 None 表示本候选当前不可认领，直接跳过且不发
    SQL。正确性只依赖数据库条件：每条 UPDATE 必须自带「尚未被他人认领」的谓词，
    命中与否以 rowcount 判定，因此两个并发认领者最多一个成功。

    事务形态按方言分支，且**只**在本函数内部分支（`db/tx.row_locks_hold_until_commit`）：

    - PostgreSQL：候选读取带 `FOR UPDATE SKIP LOCKED`，行锁持续到提交，因此并发认领
      者的候选集天然互不相交，CAS 不再空转。前提是这个事务里不再插入任何慢路径——
      `claim_cas` 被刻意定义为**同步**回调，构造 SQL 之外不做任何 await，也就无法把
      Runtime/Chromium 之类的耗时夹进持锁窗口。
    - SQLite：方言把 `FOR UPDATE`（含 `SKIP LOCKED`）静默丢弃成普通 SELECT，行锁不存在，
      读事务还会在下一条 UPDATE 时升级失败，因此读取后先结束读事务，再靠 CAS 竞争。
      该分支的 SQL 与认领语义与收口前完全一致，唯一变化是候选集不再互斥。

    其他约束：全部尝试结束后统一提交，即使一条也没抢到也要提交——失败的 CAS 已经
    开启了写事务，不提交会把写锁带给调用方的下一次操作。`max_claims` 供「扫描多候选、
    只取一个」的领取者使用：达到数量即停止，避免把已 CAS 成功的任务留在无人执行的
    running 状态。
    """

    # 同一条查询构造在 SQLite 上编译成普通 SELECT，因此不需要按方言分叉查询本身。
    locking_query = candidate_query.with_for_update(of=model, skip_locked=True)
    rows = list((await session.execute(locking_query.limit(max(1, candidate_limit)))).all())
    if not row_locks_hold_until_commit(session):
        await commit_end_read(session)

    claimed_rows: list[Row[Any]] = []
    for row in rows:
        statement = claim_cas(row)
        if statement is None:
            continue
        result = await session.execute(statement.execution_options(synchronize_session=False))
        if (result.rowcount or 0) == 1:
            claimed_rows.append(row)
            if max_claims is not None and len(claimed_rows) >= max_claims:
                break
    await session.commit()
    return claimed_rows


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
    """以条件 UPDATE 原子认领 pending 任务，返回当前执行者实际取得的任务 ID。

    认领时序由 `claim_rows_by_cas` 提供；本函数只负责标准队列模型的列名与取值：
    `worker_id` / `heartbeat_at` / `cancel_requested_at` / `error_code`。列命名不同或
    需要额外认领条件的任务模型（如 ProjectBuildJob）直接复用 `claim_rows_by_cas`。
    """

    claimed_at = now or utc_now()
    lease_expires_at = claimed_at + timedelta(seconds=max(1, lease_seconds))
    query = candidate_query
    if query is None:
        query = (
            select(model.id)
            .where(model.status == "pending", model.cancel_requested_at.is_(None))
            .order_by(model.created_at.asc(), model.id.asc())
        )

    def _claim_cas(row: Row[Any]) -> Update:
        return (
            update(model)
            .where(
                model.id == row[0],
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
        )

    claimed_rows = await claim_rows_by_cas(
        session,
        model,
        candidate_query=query,
        candidate_limit=limit,
        claim_cas=_claim_cas,
    )
    return [int(row[0]) for row in claimed_rows]


async def renew_running_job_lease(
    session: AsyncSession,
    model: type[Any],
    *,
    job_id: int,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
    owner_attr: str = "worker_id",
    heartbeat_attr: str = "heartbeat_at",
    not_after: datetime | None = None,
) -> bool:
    """仅允许当前未过期租约的拥有者续租，避免旧 Worker 重新激活失效任务。

    `owner_attr` / `heartbeat_attr` 允许 ProjectBuildJob 等使用
    `lease_owner` / `claimed_at` 命名的任务模型复用同一套 CAS 续租语义。
    `not_after` 用于绝对期限：新租约被裁剪到该时刻之后，越过即拒绝续租，
    使续租与领取/终态共用同一个 wall-clock 上界。
    """

    heartbeat_at = now or utc_now()
    owner_column = getattr(model, owner_attr)
    lease_expires_at = heartbeat_at + timedelta(seconds=max(1, lease_seconds))
    if not_after is not None and lease_expires_at > not_after:
        lease_expires_at = not_after
    if lease_expires_at <= heartbeat_at:
        # 绝对期限已经吃掉全部租约预算：此刻起不再承认所有权。
        return False
    values = {
        heartbeat_attr: heartbeat_at,
        "lease_expires_at": lease_expires_at,
    }
    result = await session.execute(
        update(model)
        .where(
            model.id == job_id,
            model.status == "running",
            owner_column == worker_id,
            model.lease_expires_at.is_not(None),
            model.lease_expires_at > heartbeat_at,
        )
        .values(**values)
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
    owner_attr: str = "worker_id",
    cancel_attr: str = "cancel_requested_at",
    extra_conditions: list[Any] | None = None,
) -> bool:
    """按任务 ID、拥有者和可选未过期租约迁移 running 任务，避免旧 Worker 覆盖新状态。

    `owner_attr` / `cancel_attr` 支持非标准命名的任务模型；`extra_conditions`
    供领域服务附加产物指针、attempt 围栏等领域条件。
    """

    owner_column = getattr(model, owner_attr)
    conditions = [model.id == job_id, model.status == "running", owner_column == worker_id]
    if require_not_cancelled:
        conditions.append(getattr(model, cancel_attr).is_(None))
    if require_active_lease:
        conditions.extend([model.lease_expires_at.is_not(None), model.lease_expires_at > utc_now()])
    if extra_conditions:
        conditions.extend(extra_conditions)
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

    # 定时恢复在空闲期会频繁执行：先只读筛选，无命中时不发任何 UPDATE，避免空转写放大。
    # 后续 UPDATE 仍带过期条件，以抵御筛选之后的并发变化。
    candidates = list(
        (
            await session.execute(
                select(model.id, model.cancel_requested_at, model.attempt_count).where(*base_conditions)
            )
        ).all()
    )
    if not candidates:
        await commit_end_read(session)
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
