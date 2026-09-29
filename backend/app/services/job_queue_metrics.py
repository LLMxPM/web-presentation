"""文件功能：汇总领域任务与执行层观测，避免把 ExternalTask 投影重复算入总量。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import normalize_utc, utc_now
from app.services.job_queue_metric_specs import QUEUE_METRIC_SPECS
from app.services.job_queue_observation import observe_queue


async def snapshot_job_queue_metrics(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, Any]:
    """返回无业务标识的聚合观测；totals 是领域任务行数，不是去重的用户请求数。"""

    moment = normalize_utc(now or utc_now())
    queues = {
        spec.name: await observe_queue(session, spec, moment)
        for spec in QUEUE_METRIC_SPECS
    }
    included = [spec.name for spec in QUEUE_METRIC_SPECS if spec.layer == "domain"]
    domains = [queues[name] for name in included]
    ages = [
        item["oldest_pending_age_seconds"]
        for item in domains
        if item["oldest_pending_age_seconds"] is not None
    ]
    return {
        "schema_version": 2,
        "checked_at": moment.isoformat(),
        "queues": queues,
        "totals": {
            "unit": "domain_job_rows",
            "included_queues": included,
            **{
                key: sum(item[key] for item in domains)
                for key in (
                    "pending",
                    "running",
                    "expired_lease_running",
                    "missing_lease_running",
                    "waiting_provider",
                )
            },
            "oldest_pending_age_seconds": max(ages, default=None),
        },
    }
