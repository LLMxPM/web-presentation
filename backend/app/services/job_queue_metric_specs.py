"""文件功能：登记队列观测的状态与租约拥有者，区分领域任务、外部投影与执行槽位。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from render_contracts.constants import (
    ATTEMPT_OCCUPYING_STATUSES,
    REQUEST_STATUS_EXECUTING,
    REQUEST_STATUS_QUEUED,
    REQUEST_STATUS_RETRY_WAIT,
)

from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_page_mutation import AiPageMutationJob
from app.models.api_mutation_job import ApiMutationJob
from app.models.asset_render_hint_backfill_job import AssetRenderHintBackfillJob
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.project_build_job import ProjectBuildJob
from app.models.render_attempt import RenderAttempt
from app.models.render_request import RenderRequest


@dataclass(frozen=True)
class QueueMetricSpec:
    """定义一个观测集合；只有 domain 层参与领域任务行数汇总。"""

    name: str
    model: type[Any]
    layer: str = "domain"
    pending: tuple[str, ...] = ("pending",)
    running: tuple[str, ...] = ("running",)
    lease: str | None = "lease_expires_at"
    created: str = "created_at"
    kind: str | None = None
    occupied_only: bool = False
    poll: str | None = None


QUEUE_METRIC_SPECS = (
    QueueMetricSpec("page_mutation", AiPageMutationJob),
    QueueMetricSpec("image_generation", AiImageGenerationJob, poll="next_poll_at"),
    QueueMetricSpec(
        "component_mutation", AiAgentExternalTask, kind="component_mutation"
    ),
    QueueMetricSpec("page_screenshot", PageScreenshotJob),
    QueueMetricSpec("project_build", ProjectBuildJob),
    QueueMetricSpec("asset_render_hint_backfill", AssetRenderHintBackfillJob),
    QueueMetricSpec("api_mutation", ApiMutationJob),
    QueueMetricSpec("external_task", AiAgentExternalTask, layer="projection"),
    QueueMetricSpec(
        "external_batch",
        AiAgentExternalBatch,
        layer="continuation",
        pending=("collecting", "waiting_tasks", "ready"),
        running=("resuming",),
    ),
    QueueMetricSpec(
        "render_request",
        RenderRequest,
        layer="execution_request",
        pending=(REQUEST_STATUS_QUEUED, REQUEST_STATUS_RETRY_WAIT),
        running=(REQUEST_STATUS_EXECUTING,),
        lease=None,
    ),
    QueueMetricSpec(
        "render_attempt",
        RenderAttempt,
        layer="execution_slot",
        pending=(),
        running=tuple(sorted(ATTEMPT_OCCUPYING_STATUSES)),
        created="reserved_at",
        occupied_only=True,
    ),
)
