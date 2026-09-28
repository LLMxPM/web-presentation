"""文件功能：只读测量数据库认领竞争基线（吞吐、无效 CAS、往返、tick 延迟），不写业务数据。

脚本在目标库上自建一次性合成队列表，测完即删；必须指向**可丢弃的测量库**，
禁止对生产库或开发主库运行。数字用于 claim 事务形态的同口径对比，不是业务 SLA。

用法（与 §9.4 同口径复测）：

    uv run --project backend python -m app.scripts.measure_claim_contention \\
        --database-url postgresql+asyncpg://user:pass@localhost:5432/claim_measure \\
        --workers 1,4,8,16 --limit 1,4 --jobs 3000 --window-seconds 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import DateTime, Integer, String, Text, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.time_utils import utc_now
from app.services.durable_job_lease_service import claim_rows_by_cas

ShapeName = Literal["current", "cross_commit_cas"]

# 与标准队列模型同构：刻意避开外键与业务谓词，使全部 worker 竞争同一批头部候选。
_TABLE_PREFIX = "claim_measure_jobs"


class MeasureBase(DeclarativeBase):
    """测量专用声明基类，不挂载业务模型元数据。"""


class MeasureJob(MeasureBase):
    """与标准持久化队列同列词汇的合成任务，仅供认领基线测量。"""

    __tablename__ = _TABLE_PREFIX

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


@dataclass(slots=True)
class ShapeResult:
    """单档并发下的认领测量结果。"""

    shape: str
    workers: int
    limit: int
    claimed: int
    updates: int
    window_seconds: float
    tick_seconds: list[float] = field(default_factory=list)
    duplicate_claims: int = 0

    @property
    def throughput_per_second(self) -> float:
        """窗口内平均认领吞吐。"""

        return self.claimed / self.window_seconds if self.window_seconds > 0 else 0.0

    @property
    def invalid_cas_ratio(self) -> float:
        """无效 CAS 占比：发出的 UPDATE 数减去实际认领数。"""

        if self.updates <= 0:
            return 0.0
        return max(0.0, (self.updates - self.claimed) / self.updates)

    @property
    def roundtrips_per_claim(self) -> float:
        """每认领一次的 UPDATE 往返数（不含候选 SELECT）。"""

        return self.updates / self.claimed if self.claimed else 0.0

    @property
    def tick_p50_ms(self) -> float:
        """单次认领尝试耗时 P50（毫秒）。"""

        return _percentile(self.tick_seconds, 0.50) * 1000

    @property
    def tick_p95_ms(self) -> float:
        """单次认领尝试耗时 P95（毫秒）。"""

        return _percentile(self.tick_seconds, 0.95) * 1000


def _percentile(values: Sequence[float], quantile: float) -> float:
    """计算近似分位数；空序列返回 0。"""

    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


async def _prepare_table(engine: AsyncEngine, *, jobs: int) -> None:
    """重建合成表并播种指定数量的 pending 任务，`created_at` 单调递增。"""

    async with engine.begin() as conn:
        await conn.run_sync(MeasureBase.metadata.drop_all, checkfirst=True)
        await conn.run_sync(MeasureBase.metadata.create_all)

    base = utc_now()
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all(
            MeasureJob(
                status="pending",
                attempt_count=0,
                created_at=base + timedelta(milliseconds=index),
            )
            for index in range(jobs)
        )
        await session.commit()


async def _cleanup_table(engine: AsyncEngine) -> None:
    """删除合成表，测量库不留残留。"""

    async with engine.begin() as conn:
        await conn.run_sync(MeasureBase.metadata.drop_all, checkfirst=True)


async def _run_current_claim(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    stats: dict[str, int],
) -> list[Any]:
    """生产形态：委托 `claim_rows_by_cas`，与 `claim_pending_jobs` 同时序。"""

    stats["calls"] += 1
    now = utc_now()
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    query = (
        select(MeasureJob.id, MeasureJob.created_at)
        .where(MeasureJob.status == "pending", MeasureJob.cancel_requested_at.is_(None))
        .order_by(MeasureJob.created_at.asc(), MeasureJob.id.asc())
    )

    def _claim_cas(row: Any) -> Any:
        stats["updates"] += 1
        return (
            update(MeasureJob)
            .where(
                MeasureJob.id == row[0],
                MeasureJob.status == "pending",
                MeasureJob.cancel_requested_at.is_(None),
            )
            .values(
                status="running",
                worker_id=worker_id,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                attempt_count=MeasureJob.attempt_count + 1,
                error_code=None,
                error_message=None,
                started_at=now,
                finished_at=None,
            )
        )

    return await claim_rows_by_cas(
        session,
        MeasureJob,
        candidate_query=query,
        candidate_limit=limit,
        claim_cas=_claim_cas,
        max_claims=limit,
    )


async def _cross_commit_cas_once(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    stats: dict[str, int],
) -> list[int]:
    """收口前形态：跨 commit 逐条 CAS，用于与生产形态同口径对比。

    刻意不写 `SKIP LOCKED`：CP3 之前候选读取不依赖行锁互斥，全部 worker
    按 `created_at` 抢同一批头部候选，靠 CAS 竞争。此处复现的是「收益为零」
    论证所对照的基线，不是「跨事务 + SKIP LOCKED」字面处方。
    """

    from app.db.tx import commit_end_read

    stats["calls"] += 1
    now = utc_now()
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    query = (
        select(MeasureJob.id)
        .where(MeasureJob.status == "pending", MeasureJob.cancel_requested_at.is_(None))
        .order_by(MeasureJob.created_at.asc(), MeasureJob.id.asc())
        .limit(max(1, limit))
        .with_for_update(of=MeasureJob)
    )
    rows = list((await session.execute(query)).all())
    await commit_end_read(session)
    claimed: list[int] = []
    for row in rows:
        stats["updates"] += 1
        result = await session.execute(
            update(MeasureJob)
            .where(
                MeasureJob.id == row[0],
                MeasureJob.status == "pending",
                MeasureJob.cancel_requested_at.is_(None),
            )
            .values(
                status="running",
                worker_id=worker_id,
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                attempt_count=MeasureJob.attempt_count + 1,
                error_code=None,
                error_message=None,
                started_at=now,
                finished_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        if (result.rowcount or 0) == 1:
            claimed.append(int(row[0]))
    await session.commit()
    return claimed


async def _run_worker(
    factory: async_sessionmaker[AsyncSession],
    *,
    worker_id: str,
    shape: str,
    limit: int,
    lease_seconds: int,
    execute_ms: float,
    deadline: float,
    stats: dict[str, int],
    claimed_ids: list[int],
    tick_seconds: list[float],
) -> None:
    """持续认领直到窗口结束，记录 tick 耗时与认领 ID。"""

    while time.monotonic() < deadline:
        started = time.perf_counter()
        async with factory() as session:
            if shape == "current":
                rows = await _run_current_claim(
                    session,
                    worker_id=worker_id,
                    limit=limit,
                    lease_seconds=lease_seconds,
                    stats=stats,
                )
            else:
                rows = await _cross_commit_cas_once(
                    session,
                    worker_id=worker_id,
                    limit=limit,
                    lease_seconds=lease_seconds,
                    stats=stats,
                )
        elapsed = time.perf_counter() - started
        tick_seconds.append(elapsed)
        for row in rows:
            claimed_ids.append(int(row[0] if not isinstance(row, int) else row))
        if rows and execute_ms > 0:
            await asyncio.sleep(execute_ms / 1000.0)


async def measure_shape(
    engine: AsyncEngine,
    *,
    shape: ShapeName,
    workers: int,
    limit: int,
    jobs: int,
    window_seconds: float,
    execute_ms: float,
    lease_seconds: int,
) -> ShapeResult:
    """在干净表上跑一档并发，返回该形态的测量结果。"""

    await _prepare_table(engine, jobs=jobs)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    stats = {"calls": 0, "updates": 0}
    claimed_ids: list[int] = []
    tick_seconds: list[float] = []
    deadline = time.monotonic() + window_seconds

    await asyncio.gather(
        *(
            _run_worker(
                factory,
                worker_id=f"measure-worker-{index}",
                shape=shape,
                limit=limit,
                lease_seconds=lease_seconds,
                execute_ms=execute_ms,
                deadline=deadline,
                stats=stats,
                claimed_ids=claimed_ids,
                tick_seconds=tick_seconds,
            )
            for index in range(workers)
        )
    )

    # 正确性：同一任务不得被认领两次。
    duplicate_claims = len(claimed_ids) - len(set(claimed_ids))
    async with factory() as session:
        running = (
            await session.execute(
                select(MeasureJob.id).where(MeasureJob.status == "running")
            )
        ).scalars().all()
    # 以库内 running 为准校验一致性；差异记入 duplicate 旁路说明。
    if len(set(claimed_ids)) != len(running):
        print(
            f"警告：内存认领数 {len(set(claimed_ids))} 与库内 running {len(running)} 不一致",
            file=sys.stderr,
        )

    return ShapeResult(
        shape=shape,
        workers=workers,
        limit=limit,
        claimed=len(claimed_ids),
        updates=stats["updates"],
        window_seconds=window_seconds,
        tick_seconds=tick_seconds,
        duplicate_claims=duplicate_claims,
    )


def _parse_int_list(raw: str) -> list[int]:
    """解析 `1,4,8` 形式的整数列表。"""

    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("至少需要一个整数")
    try:
        return [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"非法整数列表：{raw}") from exc


def format_result(result: ShapeResult) -> str:
    """格式化单档结果为单行摘要。"""

    return (
        f"{result.shape:16} workers={result.workers:2d} limit={result.limit} "
        f"claimed={result.claimed:5d} thr={result.throughput_per_second:6.1f}/s "
        f"invalid={result.invalid_cas_ratio * 100:5.1f}% "
        f"rt/claim={result.roundtrips_per_claim:5.2f} "
        f"tick_p50={result.tick_p50_ms:7.1f}ms tick_p95={result.tick_p95_ms:7.1f}ms "
        f"dup={result.duplicate_claims}"
    )


async def _amain(argv: list[str] | None = None) -> int:
    """解析参数并执行测量矩阵；只读业务库，合成表测后删除。"""

    parser = argparse.ArgumentParser(
        description="测量数据库认领竞争基线（合成表，用后即删）",
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="可丢弃的测量库连接串；禁止指向生产库或开发主库。",
    )
    parser.add_argument(
        "--shape",
        default="current,cross_commit_cas",
        help="逗号分隔形态：current=生产 claim_rows_by_cas，cross_commit_cas=收口前跨 commit CAS。",
    )
    parser.add_argument("--workers", type=_parse_int_list, default=[1, 4, 8, 16])
    parser.add_argument("--limit", type=_parse_int_list, default=[1, 4])
    parser.add_argument("--jobs", type=int, default=3000, help="每次测量播种的 pending 数。")
    parser.add_argument("--window-seconds", type=float, default=10.0, help="每档并发的测量窗口。")
    parser.add_argument(
        "--execute-ms",
        type=float,
        default=10.0,
        help="认领后模拟执行毫秒数，只影响绝对吞吐。",
    )
    parser.add_argument("--lease-seconds", type=int, default=300)
    args = parser.parse_args(argv)

    shapes = [part.strip() for part in args.shape.split(",") if part.strip()]
    for name in shapes:
        if name not in {"current", "cross_commit_cas"}:
            print(f"未知形态：{name}", file=sys.stderr)
            return 2

    engine = create_async_engine(args.database_url, pool_pre_ping=True)
    try:
        await _prepare_table(engine, jobs=1)
        await _cleanup_table(engine)

        results: list[ShapeResult] = []
        for shape in shapes:
            for limit in args.limit:
                for workers in args.workers:
                    result = await measure_shape(
                        engine,
                        shape=shape,  # type: ignore[arg-type]
                        workers=workers,
                        limit=limit,
                        jobs=args.jobs,
                        window_seconds=args.window_seconds,
                        execute_ms=args.execute_ms,
                        lease_seconds=args.lease_seconds,
                    )
                    results.append(result)
                    print(format_result(result), flush=True)
    finally:
        await _cleanup_table(engine)
        await engine.dispose()

    # 汇总对照：同 limit 下 current / cross_commit_cas 的吞吐倍率。
    print()
    print("对照（current / cross_commit_cas 吞吐倍率，按 limit）：")
    for limit in args.limit:
        for workers in args.workers:
            current = next(
                (r for r in results if r.shape == "current" and r.limit == limit and r.workers == workers),
                None,
            )
            legacy = next(
                (
                    r
                    for r in results
                    if r.shape == "cross_commit_cas" and r.limit == limit and r.workers == workers
                ),
                None,
            )
            if current is None or legacy is None or legacy.throughput_per_second <= 0:
                continue
            ratio = current.throughput_per_second / legacy.throughput_per_second
            print(f"  limit={limit} workers={workers:2d}: {ratio:.2f}x")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""

    return asyncio.run(_amain(argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
