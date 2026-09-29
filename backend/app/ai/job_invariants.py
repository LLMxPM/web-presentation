"""文件功能：跨表任务不变量的写路径强制与审计兜底（WS-A4）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.task_states import (
    EXTERNAL_TASK_TERMINAL_STATUSES,
    REQUIREMENT_ACTIVE_STATUSES,
    ensure_state_transition,
    REQUIREMENT_TRANSITIONS,
)
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.ai_agent_runtime import AiAgentRequirement
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask


# ---------------------------------------------------------------------------
# INV-1：requirement.status = resolving ⇔ 有效租约的 batch.status = resuming
# ---------------------------------------------------------------------------


def assert_inv1_requirement_batch(
    *,
    requirement: AiAgentRequirement | None,
    batch: AiAgentExternalBatch | None,
    now: datetime | None = None,
    require_active_lease: bool = True,
) -> None:
    """校验 Requirement 与 Batch 的等待态耦合（INV-1）。

    - `requirement.resolving` 必须对应 `batch.resuming`；
    - `require_active_lease` 时，resuming Batch 还必须持有未过期租约。
    写路径在同事务改完两侧后调用；不满足直接抛错，避免半截状态入库。
    """

    if requirement is None or batch is None:
        # 无关联对时由调用方决定是否允许；此处不越权裁决。
        return
    if requirement.status == "resolving":
        if batch.status != "resuming":
            raise AppException(
                status_code=409,
                code="AI_INV1_REQUIREMENT_BATCH_MISMATCH",
                detail="Requirement 处于 resolving，但 Batch 不是 resuming。",
                data={"requirement_id": requirement.requirement_id, "batch_id": batch.batch_id},
            )
        if require_active_lease:
            moment = now or utc_now()
            if batch.lease_expires_at is None or batch.lease_expires_at <= moment:
                raise AppException(
                    status_code=409,
                    code="AI_INV1_RESUMING_LEASE_EXPIRED",
                    detail="resuming Batch 没有有效租约，不得维持 resolving。",
                    data={"batch_id": batch.batch_id},
                )
    elif requirement.status in REQUIREMENT_ACTIVE_STATUSES and batch.status == "resuming":
        # pending 配 resuming 不是合法组合（claim 时应同时置 resolving）。
        if requirement.status == "pending":
            raise AppException(
                status_code=409,
                code="AI_INV1_REQUIREMENT_BATCH_MISMATCH",
                detail="Batch 处于 resuming，但 Requirement 仍是 pending。",
                data={"requirement_id": requirement.requirement_id, "batch_id": batch.batch_id},
            )


async def load_requirement_batch_pair(
    session: AsyncSession,
    *,
    requirement_id: str | None,
    batch_id: str | None = None,
    run_id: str | None = None,
) -> tuple[AiAgentRequirement | None, AiAgentExternalBatch | None]:
    """按 requirement_id / batch_id / run_id 载入关联对，供 INV-1 校验。"""

    requirement: AiAgentRequirement | None = None
    batch: AiAgentExternalBatch | None = None
    if requirement_id:
        requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == requirement_id)
        )
    if batch_id:
        batch = await session.scalar(select(AiAgentExternalBatch).where(AiAgentExternalBatch.batch_id == batch_id))
    elif requirement is not None and requirement_id:
        batch = await session.scalar(
            select(AiAgentExternalBatch).where(AiAgentExternalBatch.requirement_id == requirement_id)
        )
    elif run_id:
        batch = await session.scalar(
            select(AiAgentExternalBatch)
            .where(AiAgentExternalBatch.run_id == run_id, AiAgentExternalBatch.status == "resuming")
            .limit(1)
        )
    return requirement, batch


# ---------------------------------------------------------------------------
# INV-3：领域 Job 终态 ⇒ ExternalTask 已写穿终态
# ---------------------------------------------------------------------------


async def finalize_external_backed_job(
    session: AsyncSession,
    *,
    job: Any,
    status: str,
    values: dict[str, Any] | None = None,
    sync_external: bool = True,
) -> bool:
    """把领域 Job 收敛到终态，并在同一事务写穿 ExternalTask（INV-3）。

    `status` 必须是 succeeded/failed/cancelled。调用方负责已持有租约围栏；
    本函数保证「Job 终态」与「Task 终态投影」不会只写一半。
    """

    from app.ai.external_task_control import sync_external_task_from_domain_job

    if status not in EXTERNAL_TASK_TERMINAL_STATUSES:
        raise ValueError(f"INV3_TERMINAL_STATUS_INVALID:{status}")
    current = str(getattr(job, "status", "") or "")
    if current not in EXTERNAL_TASK_TERMINAL_STATUSES:
        ensure_state_transition(
            current=current,
            target=status,
            transitions={
                "pending": frozenset(EXTERNAL_TASK_TERMINAL_STATUSES | {"running", "waiting_provider"}),
                "running": frozenset(EXTERNAL_TASK_TERMINAL_STATUSES | {"pending", "waiting_provider"}),
                "waiting_provider": frozenset(EXTERNAL_TASK_TERMINAL_STATUSES | {"pending"}),
            },
            entity="domain_job",
        )
    job.status = status
    now = utc_now()
    if values:
        for key, value in values.items():
            setattr(job, key, value)
    if not getattr(job, "finished_at", None):
        job.finished_at = now
    if sync_external:
        await sync_external_task_from_domain_job(session, job=job)
    return True


async def assert_inv3_job_task_synced(
    session: AsyncSession,
    *,
    job: Any,
) -> bool:
    """审计：领域 Job 终态时对应 ExternalTask 必须已是终态（INV-3 兜底）。"""

    domain_status = str(getattr(job, "status", "") or "")
    if domain_status not in EXTERNAL_TASK_TERMINAL_STATUSES:
        return True
    task = await session.scalar(
        select(AiAgentExternalTask).where(
            AiAgentExternalTask.run_id == job.run_id,
            AiAgentExternalTask.tool_call_id == job.tool_call_id,
        )
    )
    if task is None:
        return True
    return task.status in EXTERNAL_TASK_TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# INV-5：产物 attempt_id 必须等于 Job 当前 attempt
# ---------------------------------------------------------------------------


def assert_inv5_attempt_fence(
    *,
    job: Any,
    attempt_id: str | None,
    require_active_lease: bool = True,
    lease_owner: str | None = None,
    now: datetime | None = None,
    require_owner_present: bool = True,
) -> None:
    """校验产物/结果归属的 attempt 围栏（INV-5）。

    迟到上传或迟到完成不得覆盖新 attempt 的结果。语义与构建产物提升一致：
    - 任务必须仍可执行（pending/running）；
    - attempt 必须匹配；
    - `require_owner_present` 时必须已有租约持有者；
    - `lease_owner` 传入时必须与持有者一致；
    - `require_active_lease` 时，显式租约不得已过期（缺省过期列视为未约束）。
    """

    status = str(getattr(job, "status", "") or "")
    if status not in {"pending", "running"}:
        raise AppException(
            status_code=409,
            code="BUILD_JOB_NOT_EXECUTABLE",
            detail="任务已结束，迟到结果不得覆盖已有结果。",
            data={"job_id": getattr(job, "id", None), "status": status},
        )
    normalized_attempt = str(attempt_id or "").strip()
    job_attempt = str(getattr(job, "attempt_id", "") or "").strip()
    if not normalized_attempt or normalized_attempt != job_attempt:
        raise AppException(
            status_code=409,
            code="BUILD_ATTEMPT_MISMATCH",
            detail="产物 attempt 与当前任务不一致，迟到结果不得覆盖新结果。",
            data={"job_id": getattr(job, "id", None), "attempt_id": job_attempt or None},
        )
    owner = getattr(job, "lease_owner", getattr(job, "worker_id", None))
    if require_owner_present and not owner:
        raise AppException(
            status_code=409,
            code="BUILD_LEASE_MISSING",
            detail="任务当前没有有效租约，产物不得提升为最终结果。",
            data={"job_id": getattr(job, "id", None), "status": status},
        )
    if lease_owner and str(lease_owner) != str(owner):
        raise AppException(
            status_code=409,
            code="BUILD_LEASE_OWNER_MISMATCH",
            detail="结果提交者与当前租约持有者不一致。",
            data={"job_id": getattr(job, "id", None)},
        )
    if require_active_lease:
        moment = now or utc_now()
        expires = getattr(job, "lease_expires_at", None)
        if expires is not None and expires <= moment:
            raise AppException(
                status_code=409,
                code="BUILD_LEASE_EXPIRED",
                detail="任务租约已过期，产物不得提升为最终结果。",
                data={"job_id": getattr(job, "id", None)},
            )


# ---------------------------------------------------------------------------
# 审计兜底：组合检查 INV-1/INV-3，供诊断 CLI 与巡检调用
# ---------------------------------------------------------------------------


async def audit_cross_table_invariants(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, list[str]]:
    """只读巡检跨表不变量；返回违规摘要，不自动修复。

    写路径已强制时本函数应为空结果；非空表示历史坏数据或旁路写入，
    交由 `audit_external_state_consistency` 等修复流程处理。
    """

    moment = now or utc_now()
    violations: dict[str, list[str]] = {"inv1": [], "inv3": []}

    resuming_batches = list(
        (
            await session.scalars(
                select(AiAgentExternalBatch).where(AiAgentExternalBatch.status == "resuming")
            )
        ).all()
    )
    for batch in resuming_batches:
        requirement = None
        if batch.requirement_id:
            requirement = await session.scalar(
                select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == batch.requirement_id)
            )
        try:
            assert_inv1_requirement_batch(
                requirement=requirement,
                batch=batch,
                now=moment,
                require_active_lease=False,
            )
        except AppException as exc:
            violations["inv1"].append(f"{batch.batch_id}:{exc.code}")
        if requirement is not None and requirement.status == "resolving":
            if batch.lease_expires_at is None or batch.lease_expires_at <= moment:
                violations["inv1"].append(f"{batch.batch_id}:AI_INV1_RESUMING_LEASE_EXPIRED")

    resolving_requirements = list(
        (
            await session.scalars(
                select(AiAgentRequirement).where(AiAgentRequirement.status == "resolving")
            )
        ).all()
    )
    for requirement in resolving_requirements:
        batch = await session.scalar(
            select(AiAgentExternalBatch).where(AiAgentExternalBatch.requirement_id == requirement.requirement_id)
        )
        if batch is None or batch.status != "resuming":
            violations["inv1"].append(f"{requirement.requirement_id}:AI_INV1_NO_RESUMING_BATCH")

    return violations
