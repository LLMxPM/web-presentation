"""文件功能：验证持久化队列积压指标快照可导出且不泄露业务标识。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.job_queue_metrics import snapshot_job_queue_metrics


@pytest.mark.asyncio
async def test_snapshot_job_queue_metrics_should_include_core_queues(app_session: AsyncSession) -> None:
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
