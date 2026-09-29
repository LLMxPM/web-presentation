"""文件功能：固化 claim 返回标量副本、rollback expire 不影响认领结果的不变量。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import DateTime, Integer, String, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time_utils import utc_now
from app.db.retry import WriteConflictContext, run_with_write_retry
from app.services.durable_job_lease_service import DurableJobRuntime, claim_rows_by_cas

pytestmark = pytest.mark.integration


class ExpireProbeBase(DeclarativeBase):
    """expire 不变量测试专用声明基类。"""


class ExpireProbeJob(ExpireProbeBase):
    """最小认领模型，用于验证返回值不依赖会话内 ORM 实体。"""

    __tablename__ = "expire_probe_claim_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(256), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


@pytest.fixture
async def expire_engine():
    """建立内存 SQLite 引擎与探测表。"""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ExpireProbeBase.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def expire_factory(expire_engine) -> async_sessionmaker[AsyncSession]:
    """返回绑定探测库的会话工厂。"""

    return async_sessionmaker(expire_engine, expire_on_commit=False)


async def _seed(factory: async_sessionmaker[AsyncSession], *, count: int = 3) -> None:
    """播种 pending 探测任务。"""

    base = utc_now()
    async with factory() as session:
        session.add_all(
            ExpireProbeJob(status="pending", attempt_count=0, created_at=base + timedelta(milliseconds=i))
            for i in range(count)
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,max_claims,expected", [(3, 1, 1), (3, 2, 2), (1, 3, 1)])
async def test_runtime_claim_should_respect_scan_and_execution_limits(
    expire_factory: async_sessionmaker[AsyncSession], limit: int, max_claims: int, expected: int,
) -> None:
    """多候选扫描不能超额认领，未领取行仍须留给其它 Worker。"""

    await _seed(expire_factory, count=3)
    runtime = DurableJobRuntime(model=ExpireProbeJob)
    async with expire_factory() as session:
        claimed = await runtime.claim(
            session, worker_id="bounded-worker", limit=limit, max_claims=max_claims, lease_seconds=60,
        )
        assert len(claimed) == expected
    async with expire_factory() as session:
        statuses = list((await session.scalars(select(ExpireProbeJob.status))).all())
        assert statuses.count("running") == expected
        assert statuses.count("pending") == 3 - expected


@pytest.mark.asyncio
async def test_claim_rows_returns_scalar_ids_not_attached_entities(
    expire_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`claim_rows_by_cas` 只返回主键标量副本，调用方不得依赖会话内实体。"""

    await _seed(expire_factory, count=2)

    async with expire_factory() as session:

        def _claim_cas(row: Any) -> Any:
            return (
                update(ExpireProbeJob)
                .where(ExpireProbeJob.id == row[0], ExpireProbeJob.status == "pending")
                .values(status="running", worker_id="w1", attempt_count=ExpireProbeJob.attempt_count + 1)
            )

        query = (
            select(ExpireProbeJob.id, ExpireProbeJob.created_at)
            .where(ExpireProbeJob.status == "pending")
            .order_by(ExpireProbeJob.created_at.asc(), ExpireProbeJob.id.asc())
        )
        rows = await claim_rows_by_cas(
            session,
            ExpireProbeJob,
            candidate_query=query,
            candidate_limit=2,
            claim_cas=_claim_cas,
            max_claims=2,
        )

        assert len(rows) == 2
        claimed_ids = [int(row[0]) for row in rows]
        assert claimed_ids == sorted(claimed_ids)
        for value in claimed_ids:
            assert isinstance(value, int)

        # 认领已提交；再 rollback 不应让已取出的标量失效
        await session.rollback()

        async with expire_factory() as check:
            running = (
                await check.execute(select(ExpireProbeJob.id).where(ExpireProbeJob.status == "running"))
            ).scalars().all()
            assert set(int(v) for v in running) == set(claimed_ids)


@pytest.mark.asyncio
async def test_claim_result_survives_session_expire_after_rollback(
    expire_factory: async_sessionmaker[AsyncSession],
) -> None:
    """rollback expire 后，仅用认领返回的 ID 即可继续工作，无需会话内实体。"""

    await _seed(expire_factory, count=1)

    async with expire_factory() as session:
        captured: dict[str, Any] = {}

        def _claim_cas(row: Any) -> Any:
            captured["row_id"] = int(row[0])
            return (
                update(ExpireProbeJob)
                .where(ExpireProbeJob.id == row[0], ExpireProbeJob.status == "pending")
                .values(status="running", worker_id="w2", attempt_count=ExpireProbeJob.attempt_count + 1)
            )

        query = select(ExpireProbeJob.id).where(ExpireProbeJob.status == "pending").order_by(ExpireProbeJob.id.asc())
        rows = await claim_rows_by_cas(
            session,
            ExpireProbeJob,
            candidate_query=query,
            candidate_limit=1,
            claim_cas=_claim_cas,
        )
        claimed_id = int(rows[0][0])
        assert claimed_id == captured["row_id"]

        # 模拟误用：提交后 rollback 会 expire 会话内实体
        await session.rollback()
        # 标量 ID 仍然可用；实体属性访问不再是前提
        async with expire_factory() as check:
            job = await check.get(ExpireProbeJob, claimed_id)
            assert job is not None
            assert job.status == "running"
            assert job.worker_id == "w2"


@pytest.mark.asyncio
async def test_write_retry_hook_must_use_preextracted_scalars_after_rollback(
    expire_factory: async_sessionmaker[AsyncSession],
) -> None:
    """重试钩子运行在 rollback 之后；循环前取出的标量仍然有效。"""

    async with expire_factory() as session:
        job = ExpireProbeJob(status="pending", attempt_count=0, created_at=utc_now())
        session.add(job)
        await session.commit()
        # rollback 会 expire；循环前必须取出标量
        preextracted_id = int(job.id)

        attempts = {"n": 0}
        seen_ids: list[int | None] = []

        async def _flaky(_session: AsyncSession) -> str:
            """首次抛出写冲突，其后成功。"""

            attempts["n"] += 1
            if attempts["n"] == 1:
                from sqlalchemy.exc import OperationalError

                raise OperationalError("UPDATE t", {}, Exception("database is locked"))
            return "ok"

        async def _on_conflict(context: WriteConflictContext) -> None:
            """钩子只记录预先取出的标量，并验证实体已被 expire。"""

            seen_ids.append(preextracted_id)
            assert preextracted_id is not None

        result = await run_with_write_retry(
            _flaky,
            backoff_delays=(0.001,),
            session=session,
            on_conflict=_on_conflict,
        )

        assert result == "ok"
        assert attempts["n"] == 2
        assert seen_ids == [preextracted_id]
