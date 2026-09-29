"""文件功能：汇总持久化任务队列积压与租约年龄，供 /metrics/job-queues 与容量观测使用。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_page_mutation import AiPageMutationJob
from app.models.api_mutation_job import ApiMutationJob
from app.models.asset_render_hint_backfill_job import AssetRenderHintBackfillJob
from app.models.ai_external_task import AiAgentExternalTask
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.project_build_job import ProjectBuildJob
from app.models.render_request import RenderRequest


def _age_seconds(now: datetime, value: datetime | None) -> float | None:
    """计算相对 now 的年龄（秒）；缺失返回 None。"""

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0.0, (now - value).total_seconds())


async def _queue_snapshot(
    session: AsyncSession,
    *,
    name: str,
    model: type[Any],
    pending_status: str = "pending",
    running_status: str = "running",
    lease_col: str = "lease_expires_at",
    created_col: str = "created_at",
) -> dict[str, Any]:
    """统计单个队列的 pending/running/过期租约与最老 pending 年龄。"""

    now = datetime.now(timezone.utc)
    status_col = getattr(model, "status")
    lease_attr = getattr(model, lease_col, None)
    created_attr = getattr(model, created_col, None)

    pending_count = (
        await session.execute(select(func.count()).select_from(model).where(status_col == pending_status))
    ).scalar_one()
    running_count = (
        await session.execute(select(func.count()).select_from(model).where(status_col == running_status))
    ).scalar_one()

    expired_lease = 0
    if lease_attr is not None:
        expired_lease = (
            await session.execute(
                select(func.count())
                .select_from(model)
                .where(
                    status_col == running_status,
                    (lease_attr.is_(None)) | (lease_attr <= now),
                )
            )
        ).scalar_one()

    oldest_pending_age_seconds = None
    if created_attr is not None and pending_count:
        oldest = (
            await session.execute(
                select(func.min(created_attr)).select_from(model).where(status_col == pending_status)
            )
        ).scalar_one()
        oldest_pending_age_seconds = _age_seconds(now, oldest)

    return {
        "pending": int(pending_count or 0),
        "running": int(running_count or 0),
        "expired_lease_running": int(expired_lease or 0),
        "oldest_pending_age_seconds": oldest_pending_age_seconds,
    }


async def snapshot_job_queue_metrics(session: AsyncSession) -> dict[str, Any]:
    """导出主要持久化队列的积压与租约年龄快照。

    只返回聚合计数与年龄，不返回任务 payload、工作空间或用户标识。
    """

    queues = {
        "page_mutation": await _queue_snapshot(session, name="page_mutation", model=AiPageMutationJob),
        "external_task": await _queue_snapshot(
            session, name="external_task", model=AiAgentExternalTask
        ),
        "image_generation": await _queue_snapshot(
            session, name="image_generation", model=AiImageGenerationJob
        ),
        "page_screenshot": await _queue_snapshot(session, name="page_screenshot", model=PageScreenshotJob),
        "project_build": await _queue_snapshot(
            session,
            name="project_build",
            model=ProjectBuildJob,
            lease_col="lease_expires_at",
        ),
        "asset_render_hint_backfill": await _queue_snapshot(
            session, name="asset_render_hint_backfill", model=AssetRenderHintBackfillJob
        ),
        "api_mutation": await _queue_snapshot(session, name="api_mutation", model=ApiMutationJob),
        "render_request": await _queue_snapshot(session, name="render_request", model=RenderRequest),
    }
    totals = {
        "pending": sum(item["pending"] for item in queues.values()),
        "running": sum(item["running"] for item in queues.values()),
        "expired_lease_running": sum(item["expired_lease_running"] for item in queues.values()),
        "oldest_pending_age_seconds": max(
            (item["oldest_pending_age_seconds"] or 0.0) for item in queues.values()
        )
        or None,
    }
    return {
        "checked_at": now_iso(),
        "queues": queues,
        "totals": totals,
    }


def now_iso() -> str:
    """统一时间戳格式，便于与 /metrics/db-write 对账。"""

    return datetime.now(timezone.utc).isoformat()
