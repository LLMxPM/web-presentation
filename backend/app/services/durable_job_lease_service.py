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
from app.services.job_runtime_vocabulary import STANDARD_JOB_VOCABULARY, JobColumnVocabulary


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
    vocabulary: JobColumnVocabulary | None = None,
    claim_values: Callable[[Row[Any], datetime, datetime], dict[str, Any]] | None = None,
    extra_claim_conditions: Callable[[Row[Any]], list[Any]] | None = None,
) -> list[int]:
    """以条件 UPDATE 原子认领 pending 任务，返回当前执行者实际取得的任务 ID。

    认领时序由 `claim_rows_by_cas` 提供；本函数只负责列词汇与领域取值。
    新任务类型应通过 `vocabulary` + `claim_values` 注册，不再手写认领时序。

    默认取值假定「候选列含 id（位置 0）」；若词汇声明了 `lease_generation`，
    候选查询必须把代次列放在**最后一列**（默认候选查询会自动附上），CAS 才能
    按候选代次围栏。
    """

    vocab = vocabulary or STANDARD_JOB_VOCABULARY
    claimed_at = now or utc_now()
    lease_expires_at = claimed_at + timedelta(seconds=max(1, lease_seconds))
    status_col = vocab.attribute(model, vocab.status)
    cancel_col = vocab.optional_attribute(model, vocab.cancel_requested_at)
    owner_col = vocab.owner_column(model)
    heartbeat_col = vocab.heartbeat_column(model)
    attempt_col = vocab.attribute(model, vocab.attempt_count)
    error_code_col = vocab.optional_attribute(model, vocab.error_code)
    error_message_col = vocab.optional_attribute(model, vocab.error_message)
    started_col = vocab.optional_attribute(model, vocab.started_at)
    finished_col = vocab.optional_attribute(model, vocab.finished_at)
    generation_name = vocab.lease_generation if vocab.generation_column(model) is not None else None
    generation_col = vocab.generation_column(model)

    pending_conditions = [status_col == "pending"]
    if cancel_col is not None:
        pending_conditions.append(cancel_col.is_(None))

    query = candidate_query
    if query is None:
        select_cols: list[Any] = [model.id]
        if generation_col is not None:
            select_cols.append(generation_col)
        order_cols: list[Any] = []
        if hasattr(model, "created_at"):
            order_cols.append(model.created_at.asc())
        order_cols.append(model.id.asc())
        query = select(*select_cols).where(*pending_conditions).order_by(*order_cols)

    def _default_claim_values() -> dict[str, Any]:
        values: dict[str, Any] = {
            vocab.status: "running",
            vocab.owner: worker_id,
            vocab.lease_expires_at: lease_expires_at,
            vocab.heartbeat: claimed_at,
            vocab.attempt_count: attempt_col + 1,
        }
        if generation_name and generation_col is not None:
            values[generation_name] = generation_col + 1
        if error_code_col is not None:
            values[vocab.error_code] = None  # type: ignore[index]
        if error_message_col is not None:
            values[vocab.error_message] = None  # type: ignore[index]
        if started_col is not None:
            values[vocab.started_at] = claimed_at
        if finished_col is not None:
            values[vocab.finished_at] = None
        return values

    def _claim_cas(row: Row[Any]) -> Update:
        conditions = [model.id == row[0], *pending_conditions]
        if generation_name and generation_col is not None:
            conditions.append(generation_col == row[len(row) - 1])
        if extra_claim_conditions is not None:
            conditions.extend(extra_claim_conditions(row))
        values = (
            claim_values(row, claimed_at, lease_expires_at)
            if claim_values is not None
            else _default_claim_values()
        )
        return update(model).where(*conditions).values(**values)

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
    vocabulary: JobColumnVocabulary | None = None,
) -> bool:
    """请求取消任务；pending 立即终止，running 由执行者在安全边界确认。"""

    vocab = vocabulary or STANDARD_JOB_VOCABULARY
    status_col = vocab.attribute(model, vocab.status)
    cancel_name = vocab.cancel_requested_at
    cancel_col = vocab.optional_attribute(model, cancel_name)
    finished_col = vocab.optional_attribute(model, vocab.finished_at)

    requested_at = now or utc_now()
    pending_values: dict[str, Any] = {
        vocab.status: "cancelled",
        vocab.owner: None,
        vocab.lease_expires_at: None,
        vocab.heartbeat: None,
    }
    if cancel_col is not None:
        pending_values[cancel_name] = requested_at
    if finished_col is not None:
        pending_values[vocab.finished_at] = requested_at
    pending_result = await session.execute(
        update(model)
        .where(model.id == job_id, status_col == "pending")
        .values(**pending_values)
        .execution_options(synchronize_session=False)
    )
    running_result = None
    if cancel_col is not None:
        running_result = await session.execute(
            update(model)
            .where(model.id == job_id, status_col == "running", cancel_col.is_(None))
            .values(**{cancel_name: requested_at})
            .execution_options(synchronize_session=False)
        )
    await session.commit()
    pending_count = pending_result.rowcount or 0
    running_count = running_result.rowcount if running_result is not None else 0
    return pending_count + (running_count or 0) > 0


async def recover_expired_running_jobs(
    session: AsyncSession,
    model: type[Any],
    *,
    max_attempts: int,
    interrupted_error_code: str,
    interrupted_error_message: str,
    now: datetime | None = None,
    vocabulary: JobColumnVocabulary | None = None,
    recover_values: Callable[[str, Row[Any], datetime], dict[str, Any]] | None = None,
) -> DurableJobRecoverySummary:
    """只恢复租约为空或已经过期的 running 任务，并在空队列时避免发起写 DML。

    `vocabulary` 允许非标准列名（如 ProjectBuild 的 `lease_owner`/`claimed_at`）
    复用同一套过期恢复时序。`recover_values` 供领域队列覆盖默认写入（如 MutationJob
    的 generation 递增与 `next_attempt_at` 退避）；未提供时使用契约标准取值。
    """

    vocab = vocabulary or STANDARD_JOB_VOCABULARY
    # 取列对象做谓词；写入键统一用词汇里的属性名字符串，与 update().values(**kwargs) 对齐。
    status_name = vocab.status
    owner_name = vocab.owner
    heartbeat_name = vocab.heartbeat
    lease_name = vocab.lease_expires_at
    cancel_name = vocab.cancel_requested_at if vocab.optional_attribute(model, vocab.cancel_requested_at) else None
    attempt_name = vocab.attempt_count
    error_code_name = vocab.error_code if vocab.optional_attribute(model, vocab.error_code) else None
    error_message_name = vocab.error_message if vocab.optional_attribute(model, vocab.error_message) else None
    started_name = vocab.started_at if vocab.optional_attribute(model, vocab.started_at) else None
    finished_name = vocab.finished_at if vocab.optional_attribute(model, vocab.finished_at) else None

    status_col = vocab.attribute(model, status_name)
    lease_col = vocab.attribute(model, lease_name)
    attempt_col = vocab.attribute(model, attempt_name)
    cancel_col = vocab.optional_attribute(model, cancel_name) if cancel_name else None

    recovered_at = now or utc_now()
    expired = (lease_col.is_(None)) | (lease_col <= recovered_at)
    base_conditions = (status_col == "running", expired)

    # 定时恢复在空闲期会频繁执行：先只读筛选，无命中时不发任何 UPDATE，避免空转写放大。
    # 后续 UPDATE 仍带过期条件，以抵御筛选之后的并发变化。
    # 候选只取 id / attempt / cancel，按固定位置读取，避免依赖 Row 属性名。
    select_cols: list[Any] = [model.id, attempt_col]
    if cancel_col is not None:
        select_cols.insert(1, cancel_col)
    candidates = list((await session.execute(select(*select_cols).where(*base_conditions))).all())
    if not candidates:
        await commit_end_read(session)
        return DurableJobRecoverySummary()

    attempt_limit = max(1, max_attempts)
    cancel_pos = 1 if cancel_col is not None else None
    attempt_pos = 2 if cancel_col is not None else 1

    cancelled_ids: list[int] = []
    requeued_ids: list[int] = []
    failed_ids: list[int] = []
    rows_by_id: dict[int, Row[Any]] = {}
    for row in candidates:
        rid = int(row[0])
        rows_by_id[rid] = row
        is_cancelled = cancel_pos is not None and row[cancel_pos] is not None
        attempts = int(row[attempt_pos] or 0)
        if is_cancelled:
            cancelled_ids.append(rid)
        elif attempts < attempt_limit:
            requeued_ids.append(rid)
        else:
            failed_ids.append(rid)

    def _default_values(kind: str) -> dict[str, Any]:
        if kind == "cancelled":
            values: dict[str, Any] = {
                status_name: "cancelled",
                lease_name: None,
                heartbeat_name: None,
            }
            if finished_name:
                values[finished_name] = recovered_at
            return values
        if kind == "requeued":
            values = {
                status_name: "pending",
                owner_name: None,
                lease_name: None,
                heartbeat_name: None,
            }
            if error_code_name:
                values[error_code_name] = None
            if error_message_name:
                values[error_message_name] = None
            if started_name:
                values[started_name] = None
            if finished_name:
                values[finished_name] = None
            return values
        values = {
            status_name: "failed",
            lease_name: None,
            heartbeat_name: None,
        }
        if error_code_name:
            values[error_code_name] = interrupted_error_code
        if error_message_name:
            values[error_message_name] = interrupted_error_message
        if finished_name:
            values[finished_name] = recovered_at
        return values

    def _values_for(kind: str, rid: int) -> dict[str, Any]:
        if recover_values is not None:
            return recover_values(kind, rows_by_id[rid], recovered_at)
        return _default_values(kind)

    cancelled_count = 0
    requeued_count = 0
    failed_count = 0
    if cancelled_ids:
        extra = [cancel_col.is_not(None)] if cancel_col is not None else []
        cancelled = await session.execute(
            update(model)
            .where(*base_conditions, model.id.in_(cancelled_ids), *extra)
            .values(**_values_for("cancelled", cancelled_ids[0]))
            .execution_options(synchronize_session=False)
        )
        cancelled_count = int(cancelled.rowcount or 0)
    if requeued_ids:
        extra = [cancel_col.is_(None)] if cancel_col is not None else []
        requeued = await session.execute(
            update(model)
            .where(*base_conditions, model.id.in_(requeued_ids), *extra, attempt_col < attempt_limit)
            .values(**_values_for("requeued", requeued_ids[0]))
            .execution_options(synchronize_session=False)
        )
        requeued_count = int(requeued.rowcount or 0)
    if failed_ids:
        extra = [cancel_col.is_(None)] if cancel_col is not None else []
        failed = await session.execute(
            update(model)
            .where(*base_conditions, model.id.in_(failed_ids), *extra, attempt_col >= attempt_limit)
            .values(**_values_for("failed", failed_ids[0]))
            .execution_options(synchronize_session=False)
        )
        failed_count = int(failed.rowcount or 0)
    await session.commit()
    return DurableJobRecoverySummary(
        requeued_count=requeued_count,
        failed_count=failed_count,
        cancelled_count=cancelled_count,
    )


@dataclass(slots=True)
class DurableJobRuntime:
    """绑定「模型 + 列词汇 + 领域取值」的任务运行时门面（WS-A2）。

    新任务类型只注册本结构，即可获得 claim / renew / transition / cancel / recover；
    不再手写认领时序。领域差异通过回调注入，不建能力布尔层。
    """

    model: type[Any]
    vocabulary: JobColumnVocabulary = STANDARD_JOB_VOCABULARY
    # 领域认领取值：覆盖默认 status/owner/lease/heartbeat/attempt 写入
    claim_values: Callable[[Row[Any], datetime, datetime], dict[str, Any]] | None = None
    # 领域认领谓词：附加到 CAS 条件（如 deadline、expired_or_absent_lease）
    extra_claim_conditions: Callable[[Row[Any]], list[Any]] | None = None
    # 领域恢复取值：覆盖默认 pending/failed/cancelled 写入
    recover_values: Callable[[str, Row[Any], datetime], dict[str, Any]] | None = None

    async def claim(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
        candidate_query: Select[Any] | None = None,
        max_claims: int | None = None,
    ) -> list[int]:
        """认领 pending 任务；时序由 `claim_rows_by_cas` 提供。"""

        # max_claims 通过 candidate_limit 传递：候选多扫、命中即停。
        return await claim_pending_jobs(
            session,
            self.model,
            worker_id=worker_id,
            limit=limit if max_claims is None else max(limit, max_claims),
            lease_seconds=lease_seconds,
            now=now,
            candidate_query=candidate_query,
            vocabulary=self.vocabulary,
            claim_values=self.claim_values,
            extra_claim_conditions=self.extra_claim_conditions,
        )

    async def renew(
        self,
        session: AsyncSession,
        *,
        job_id: int,
        worker_id: str,
        lease_seconds: int,
        now: datetime | None = None,
        not_after: datetime | None = None,
    ) -> bool:
        """拥有者续租；列名按词汇映射。"""

        return await renew_running_job_lease(
            session,
            self.model,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            now=now,
            owner_attr=self.vocabulary.owner,
            heartbeat_attr=self.vocabulary.heartbeat,
            not_after=not_after,
        )

    async def transition(
        self,
        session: AsyncSession,
        *,
        job_id: int,
        worker_id: str,
        values: dict[str, Any],
        require_not_cancelled: bool = False,
        require_active_lease: bool = False,
        commit: bool = True,
        extra_conditions: list[Any] | None = None,
    ) -> bool:
        """按拥有者迁移 running 任务；列名按词汇映射。"""

        return await transition_owned_running_job(
            session,
            self.model,
            job_id=job_id,
            worker_id=worker_id,
            values=values,
            require_not_cancelled=require_not_cancelled,
            require_active_lease=require_active_lease,
            commit=commit,
            owner_attr=self.vocabulary.owner,
            cancel_attr=self.vocabulary.cancel_requested_at,
            extra_conditions=extra_conditions,
        )

    async def cancel(
        self,
        session: AsyncSession,
        *,
        job_id: int,
        now: datetime | None = None,
    ) -> bool:
        """请求取消；pending 立即终态，running 写取消标记。"""

        return await request_job_cancellation(
            session,
            self.model,
            job_id=job_id,
            now=now,
            vocabulary=self.vocabulary,
        )

    async def recover(
        self,
        session: AsyncSession,
        *,
        max_attempts: int,
        interrupted_error_code: str,
        interrupted_error_message: str,
        now: datetime | None = None,
    ) -> DurableJobRecoverySummary:
        """过期 running 任务恢复；可选领域写入覆盖。"""

        return await recover_expired_running_jobs(
            session,
            self.model,
            max_attempts=max_attempts,
            interrupted_error_code=interrupted_error_code,
            interrupted_error_message=interrupted_error_message,
            now=now,
            vocabulary=self.vocabulary,
            recover_values=self.recover_values,
        )
