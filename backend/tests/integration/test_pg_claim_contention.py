"""文件功能：在真实 PostgreSQL 上验证 CP3 认领事务形态（行锁、互斥、候选集不相交）。

仓库默认测试夹具强制 SQLite，本文件是 CP3 PG 分支的可选回归通道：
配置 `P4_POSTGRES_DATABASE_URL` 时执行，否则整模块 skip。
只在测量/测试库上自建合成表，不触碰业务表。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import DateTime, Integer, String, Text, delete, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time_utils import utc_now
from app.db.tx import row_locks_hold_until_commit
from app.services.durable_job_lease_service import claim_pending_jobs, claim_rows_by_cas

pytestmark = pytest.mark.integration

_PG_URL_ENV = "P4_POSTGRES_DATABASE_URL"


class PgClaimBase(DeclarativeBase):
    """PG 认领测试专用声明基类，与业务模型元数据隔离。"""


class PgClaimJob(PgClaimBase):
    """与标准持久化队列同列词汇的合成任务。"""

    __tablename__ = "pg_claim_probe_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def _require_pg_url() -> str:
    """读取 PG 测试连接串；未配置时 skip，但 CI 可用 P4_POSTGRES_REQUIRED=1 强制失败。"""

    url = os.environ.get(_PG_URL_ENV, "").strip()
    if not url:
        if os.environ.get("P4_POSTGRES_REQUIRED", "").strip() == "1":
            pytest.fail(f"CI 必须配置 {_PG_URL_ENV}，否则 CP3 的 PostgreSQL 认领分支不会被执行")
        pytest.skip(f"未配置 {_PG_URL_ENV}，跳过 PostgreSQL 认领形态用例")
    return url


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """建立一次性 PG 引擎并保证合成表清理。"""

    url = _require_pg_url()
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(PgClaimBase.metadata.drop_all, checkfirst=True)
            await conn.run_sync(PgClaimBase.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(PgClaimBase.metadata.drop_all, checkfirst=True)
        await engine.dispose()


@pytest.fixture
def pg_session_factory(pg_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """返回绑定 PG 的会话工厂。"""

    return async_sessionmaker(pg_engine, expire_on_commit=False)


async def _seed_pending(factory: async_sessionmaker[AsyncSession], *, count: int) -> list[int]:
    """播种指定数量 pending 任务，返回按创建顺序的 ID 列表。"""

    base = utc_now()
    async with factory() as session:
        jobs = [
            PgClaimJob(status="pending", attempt_count=0, created_at=base + timedelta(milliseconds=index))
            for index in range(count)
        ]
        session.add_all(jobs)
        await session.commit()
        return [int(job.id) for job in jobs]


async def _running_ids(factory: async_sessionmaker[AsyncSession]) -> set[int]:
    """读取当前 running 任务 ID 集合。"""

    async with factory() as session:
        rows = (await session.execute(select(PgClaimJob.id).where(PgClaimJob.status == "running"))).scalars()
        return {int(value) for value in rows}


@pytest.mark.asyncio
async def test_row_locks_hold_until_commit_is_true_on_postgresql(pg_engine: AsyncEngine) -> None:
    """PG 会话必须判定为「行锁持续到提交」，认领才会走同事务 SKIP LOCKED。"""

    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as session:
        assert row_locks_hold_until_commit(session) is True


@pytest.mark.asyncio
async def test_concurrent_claim_pending_jobs_never_duplicates(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """两个 worker 并发 `claim_pending_jobs`：任务只被认领一次，无重复赢家。"""

    await _seed_pending(pg_session_factory, count=8)

    async def _claim(worker_id: str) -> list[int]:
        async with pg_session_factory() as session:
            return await claim_pending_jobs(
                session,
                PgClaimJob,
                worker_id=worker_id,
                limit=3,
                lease_seconds=300,
            )

    first, second = await asyncio.gather(_claim("pg-worker-a"), _claim("pg-worker-b"))
    claimed = first + second

    assert len(claimed) == len(set(claimed)), f"重复认领：{claimed}"
    assert len(claimed) >= 1
    assert await _running_ids(pg_session_factory) == set(claimed)

    async with pg_session_factory() as session:
        for job_id in claimed:
            job = await session.get(PgClaimJob, job_id)
            assert job is not None
            assert job.status == "running"
            assert job.attempt_count == 1
            assert job.lease_expires_at is not None


@pytest.mark.asyncio
async def test_skip_locked_candidate_sets_are_disjoint(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """并发认领时 PG 分支的候选集不相交，CAS 不得空转抢同一批行。"""

    await _seed_pending(pg_session_factory, count=12)
    examined: dict[str, list[int]] = {"a": [], "b": []}

    async def _claim(worker_id: str, key: str) -> list[Any]:
        async with pg_session_factory() as session:

            def _claim_cas(row: Any) -> Any:
                examined[key].append(int(row[0]))
                return (
                    update(PgClaimJob)
                    .where(
                        PgClaimJob.id == row[0],
                        PgClaimJob.status == "pending",
                        PgClaimJob.cancel_requested_at.is_(None),
                    )
                    .values(
                        status="running",
                        worker_id=worker_id,
                        heartbeat_at=utc_now(),
                        lease_expires_at=utc_now() + timedelta(seconds=300),
                        attempt_count=PgClaimJob.attempt_count + 1,
                    )
                )

            query = (
                select(PgClaimJob.id, PgClaimJob.created_at)
                .where(PgClaimJob.status == "pending", PgClaimJob.cancel_requested_at.is_(None))
                .order_by(PgClaimJob.created_at.asc(), PgClaimJob.id.asc())
            )
            rows = await claim_rows_by_cas(
                session,
                PgClaimJob,
                candidate_query=query,
                candidate_limit=5,
                claim_cas=_claim_cas,
                max_claims=5,
            )
            return [int(row[0]) for row in rows]

    first, second = await asyncio.gather(_claim("pg-skip-a", "a"), _claim("pg-skip-b", "b"))

    seen_a = set(examined["a"])
    seen_b = set(examined["b"])
    assert seen_a and seen_b, f"两侧都应看到候选：{examined}"
    assert seen_a & seen_b == set(), f"候选集相交，SKIP LOCKED 未生效：{examined}"
    claimed = first + second
    assert len(claimed) == len(set(claimed))
    assert set(claimed) == seen_a | seen_b


@pytest.mark.asyncio
async def test_repeated_concurrent_claims_consume_jobs_without_overlap(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """多轮并发认领会逐步吃掉 pending，任意一轮都不得重复认领。"""

    await _seed_pending(pg_session_factory, count=16)
    all_claimed: list[int] = []

    for _round in range(4):
        async def _claim(worker_id: str) -> list[int]:
            async with pg_session_factory() as session:
                return await claim_pending_jobs(
                    session,
                    PgClaimJob,
                    worker_id=worker_id,
                    limit=2,
                    lease_seconds=300,
                )

        batch_a, batch_b = await asyncio.gather(
            _claim(f"pg-loop-a-{_round}"),
            _claim(f"pg-loop-b-{_round}"),
        )
        batch = batch_a + batch_b
        assert len(batch) == len(set(batch)), f"第 {_round} 轮重复认领：{batch}"
        all_claimed.extend(batch)

    assert len(all_claimed) == len(set(all_claimed))
    assert len(all_claimed) == 16
    assert await _running_ids(pg_session_factory) == set(all_claimed)


class PgClaimRun(PgClaimBase):
    """JOIN 候选查询用的父表，模拟 `ai_agent_runs` 过滤形态。"""

    __tablename__ = "pg_claim_probe_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class PgClaimJoinedJob(PgClaimBase):
    """带 run 外键语义的合成任务，验证 `FOR UPDATE OF` 不锁父表。"""

    __tablename__ = "pg_claim_probe_joined_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


@pytest.mark.asyncio
async def test_join_candidate_query_claims_without_locking_parent_rows(
    pg_engine: AsyncEngine,
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """业务谓词形态：JOIN 过滤候选时仍可并发认领，父表行不被 `FOR UPDATE OF` 锁住。"""

    from sqlalchemy import update as sa_update

    async with pg_engine.begin() as conn:
        await conn.run_sync(PgClaimRun.__table__.create, checkfirst=True)
        await conn.run_sync(PgClaimJoinedJob.__table__.create, checkfirst=True)

    try:
        base = utc_now()
        async with pg_session_factory() as session:
            waiting = PgClaimRun(status="waiting_external")
            done = PgClaimRun(status="completed")
            session.add_all([waiting, done])
            await session.flush()
            session.add_all(
                [
                    PgClaimJoinedJob(
                        run_id=waiting.id,
                        status="pending",
                        attempt_count=0,
                        created_at=base + timedelta(milliseconds=0),
                    ),
                    PgClaimJoinedJob(
                        run_id=waiting.id,
                        status="pending",
                        attempt_count=0,
                        created_at=base + timedelta(milliseconds=1),
                    ),
                    # 父状态过滤掉：不得被认领
                    PgClaimJoinedJob(
                        run_id=done.id,
                        status="pending",
                        attempt_count=0,
                        created_at=base + timedelta(milliseconds=2),
                    ),
                ]
            )
            await session.commit()

        async def _claim(worker_id: str) -> list[int]:
            async with pg_session_factory() as session:
                query = (
                    select(PgClaimJoinedJob.id, PgClaimJoinedJob.created_at)
                    .join(PgClaimRun, PgClaimRun.id == PgClaimJoinedJob.run_id)
                    .where(
                        PgClaimJoinedJob.status == "pending",
                        PgClaimJoinedJob.cancel_requested_at.is_(None),
                        PgClaimRun.status == "waiting_external",
                    )
                    .order_by(PgClaimJoinedJob.created_at.asc(), PgClaimJoinedJob.id.asc())
                )

                def _claim_cas(row: Any) -> Any:
                    return (
                        sa_update(PgClaimJoinedJob)
                        .where(
                            PgClaimJoinedJob.id == row[0],
                            PgClaimJoinedJob.status == "pending",
                        )
                        .values(
                            status="running",
                            worker_id=worker_id,
                            attempt_count=PgClaimJoinedJob.attempt_count + 1,
                            heartbeat_at=utc_now(),
                        )
                    )

                rows = await claim_rows_by_cas(
                    session,
                    PgClaimJoinedJob,
                    candidate_query=query,
                    candidate_limit=2,
                    claim_cas=_claim_cas,
                    max_claims=2,
                )
                return [int(row[0]) for row in rows]

        first, second = await asyncio.gather(_claim("join-a"), _claim("join-b"))
        claimed = first + second
        assert len(claimed) == len(set(claimed))
        assert len(claimed) == 2, f"只应认领 waiting_external 父行下的 2 条：{claimed}"

        async with pg_session_factory() as session:
            statuses = {
                int(row.id): row.status
                for row in (
                    await session.execute(select(PgClaimJoinedJob.id, PgClaimJoinedJob.status))
                ).all()
            }
            assert sum(1 for s in statuses.values() if s == "running") == 2
            # completed 父行下的 pending 不得被碰
            leftover_pending = [i for i, s in statuses.items() if s == "pending"]
            assert len(leftover_pending) == 1
    finally:
        async with pg_engine.begin() as conn:
            await conn.run_sync(PgClaimJoinedJob.__table__.drop, checkfirst=True)
            await conn.run_sync(PgClaimRun.__table__.drop, checkfirst=True)
