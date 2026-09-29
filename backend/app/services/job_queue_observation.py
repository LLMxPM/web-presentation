"""文件功能：按队列词汇执行聚合查询，所有年龄使用一次快照的统一 UTC 时刻。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import normalize_utc
from app.services.job_queue_metric_specs import QueueMetricSpec


def age_seconds(now: datetime, value: datetime | None) -> float | None:
    """返回秒数；缺少可观测时间时返回 null，不把未知当作零。"""

    return max(0.0, (now - normalize_utc(value)).total_seconds()) if value else None


async def observe_queue(
    session: AsyncSession, spec: QueueMetricSpec, now: datetime
) -> dict[str, Any]:
    """一次分组 SQL 统计一个集合，不加载 payload，租约缺列只允许显式声明。"""

    model = spec.model
    status = model.status
    created = getattr(model, spec.created)
    lease = getattr(model, spec.lease) if spec.lease else None
    poll = getattr(model, spec.poll) if spec.poll else None
    query = (
        select(
            status,
            func.count(),
            func.min(created),
            func.sum(case((lease <= now, 1), else_=0))
            if lease is not None
            else literal(0),
            func.sum(case((lease.is_(None), 1), else_=0))
            if lease is not None
            else literal(0),
            func.sum(case((poll <= now, 1), else_=0))
            if poll is not None
            else literal(0),
            func.sum(case((poll.is_(None), 1), else_=0))
            if poll is not None
            else literal(0),
            func.min(case((poll <= now, poll), else_=None))
            if poll is not None
            else literal(None),
        )
        .select_from(model)
        .group_by(status)
    )
    if spec.kind:
        query = query.where(model.kind == spec.kind)
    if spec.occupied_only:
        query = query.where(model.active_occupancy == 1)
    rows = list((await session.execute(query)).all())
    pending_rows = [row for row in rows if row[0] in spec.pending]
    running_rows = [row for row in rows if row[0] in spec.running]
    waiting = [row for row in rows if row[0] == "waiting_provider"]
    oldest = min((row[2] for row in pending_rows if row[2]), default=None)
    due = min((row[7] for row in waiting if row[7]), default=None)
    return {
        "layer": spec.layer,
        "age_origin": spec.created,
        "states": {row[0]: row[1] for row in rows},
        "pending": sum(row[1] for row in pending_rows),
        "running": sum(row[1] for row in running_rows),
        "lease_supported": lease is not None,
        "expired_lease_running": sum(row[3] for row in running_rows)
        if lease is not None
        else None,
        "missing_lease_running": sum(row[4] for row in running_rows)
        if lease is not None
        else None,
        "oldest_pending_age_seconds": age_seconds(now, oldest),
        "waiting_provider": sum(row[1] for row in waiting),
        "overdue_provider_polls": sum(row[5] for row in waiting)
        if poll is not None
        else None,
        "missing_provider_poll": sum(row[6] for row in waiting)
        if poll is not None
        else None,
        "oldest_provider_poll_overdue_seconds": age_seconds(now, due),
    }
