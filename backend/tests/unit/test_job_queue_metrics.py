"""文件功能：验证持久化队列积压指标快照可导出且不泄露业务标识。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.services.job_queue_metrics import snapshot_job_queue_metrics
from sqlalchemy.ext.asyncio import AsyncSession

from tests.unit.job_queue_metrics_seed import seed_metrics


@pytest.mark.asyncio
async def test_snapshot_job_queue_metrics_should_include_core_queues(
    app_session: AsyncSession,
) -> None:
    """空库快照应包含主要队列键与聚合计数。"""

    payload = await snapshot_job_queue_metrics(app_session)

    assert "queues" in payload and "totals" in payload
    for key in (
        "page_mutation",
        "external_task",
        "image_generation",
        "page_screenshot",
        "project_build",
        "api_mutation",
        "render_request",
    ):
        assert key in payload["queues"]
        assert payload["queues"][key]["pending"] == 0
        assert payload["queues"][key]["running"] == 0
    assert payload["totals"]["pending"] == 0
    assert "checked_at" in payload


@pytest.mark.asyncio
async def test_nonempty_snapshot_reconciles_layers_and_leases(
    app_session: AsyncSession,
) -> None:
    """非空数据证明渲染状态、租约拥有者、供应商等待与领域汇总均使用正确口径。"""
    now = datetime(2026, 9, 30, tzinfo=UTC)
    await seed_metrics(app_session, now)
    payload = await snapshot_job_queue_metrics(app_session, now=now)
    queues = payload["queues"]
    assert payload["schema_version"] == 2
    render = queues["render_request"]
    assert (render["pending"], render["running"]) == (2, 1)
    assert render["states"] == {
        "queued": 1,
        "retry_wait": 1,
        "executing": 1,
        "succeeded": 1,
    }
    assert render["oldest_pending_age_seconds"] == 90
    assert render["lease_supported"] is False
    assert render["expired_lease_running"] is None
    attempt = queues["render_attempt"]
    assert (
        attempt["running"],
        attempt["expired_lease_running"],
        attempt["missing_lease_running"],
    ) == (3, 1, 1)
    image = queues["image_generation"]
    assert (image["pending"], image["running"], image["waiting_provider"]) == (1, 2, 3)
    assert (
        image["overdue_provider_polls"],
        image["missing_provider_poll"],
        image["oldest_provider_poll_overdue_seconds"],
    ) == (1, 1, 10)
    assert (image["expired_lease_running"], image["missing_lease_running"]) == (1, 1)
    batch = queues["external_batch"]
    assert (batch["pending"], batch["running"], batch["expired_lease_running"]) == (
        1,
        1,
        1,
    )
    assert queues["component_mutation"]["states"] == {"pending": 1, "running": 1}
    totals = payload["totals"]
    assert totals["unit"] == "domain_job_rows"
    assert (totals["pending"], totals["running"], totals["waiting_provider"]) == (
        2,
        3,
        3,
    )
    assert (totals["expired_lease_running"], totals["missing_lease_running"]) == (1, 2)
    assert totals["oldest_pending_age_seconds"] == 90
    assert not {
        "external_task",
        "external_batch",
        "render_request",
        "render_attempt",
    } & set(totals["included_queues"])
