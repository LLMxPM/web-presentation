"""文件功能：用真实数据库验证 WS-A 认领校验、页面恢复投影及不变量审计的提交边界。"""

from datetime import timedelta

import pytest
from app.ai import external_task_queue, page_mutation_recovery
from app.ai.job_invariants import audit_cross_table_invariants
from app.ai.page_mutation_queue import (
    recover_interrupted_ai_page_mutation_jobs_on_startup,
)
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.ai_image_generation import AiImageGenerationJob
from app.models.ai_image_model import AiImageModelConfig, AiImageProviderConfig
from app.models.ai_page_mutation import AiPageMutationBatch, AiPageMutationJob
from httpx import AsyncClient
from sqlalchemy import select

from tests.integration.test_ai_external_task_queue import _seed_external_batch


async def test_claim_validation_failure_rolls_back_both_rows(
    authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验拒绝必须撤销 Batch 和 Requirement；下一位协调器仍可正常认领。"""

    _, requirement_id, batch_id = await _seed_external_batch(authenticated_client, suffix="inv1-rollback")
    validate = external_task_queue.assert_inv1_requirement_batch

    def reject(**kwargs) -> None:
        """确认新状态已写入事务，再模拟不变量校验拒绝。"""

        validate(**kwargs)
        raise AppException(status_code=409, code="TEST_INV1_REJECTED", detail="故障注入")

    with monkeypatch.context() as scoped:
        scoped.setattr(external_task_queue, "assert_inv1_requirement_batch", reject)
        with pytest.raises(AppException, match="故障注入"):
            await external_task_queue._claim_ready_batch(get_session_factory(), worker_id="rejected")

    async with get_session_factory()() as session:
        batch = await session.get(AiAgentExternalBatch, batch_id)
        requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == requirement_id)
        )
        assert batch.status == "ready" and batch.lease_generation == 0
        assert batch.worker_id is None and batch.lease_expires_at is None
        assert requirement.status == "pending"
    assert await external_task_queue._claim_ready_batch(get_session_factory(), worker_id="accepted") == (batch_id, 1)


@pytest.mark.parametrize("requirement_status", ["failed", "cancelled", "resolved"])
async def test_claim_should_not_commit_without_resolving_requirement(
    authenticated_client: AsyncClient, requirement_status: str,
) -> None:
    """Requirement 更新未命中时不得提交半截认领。"""

    _, _, batch_id = await _seed_external_batch(
        authenticated_client, suffix="inv1-terminal", requirement_status=requirement_status,
    )
    with pytest.raises(AppException) as caught:
        await external_task_queue._claim_ready_batch(get_session_factory(), worker_id="invalid")
    assert caught.value.code == "AI_INV1_REQUIREMENT_BATCH_MISMATCH"
    async with get_session_factory()() as session:
        batch = await session.get(AiAgentExternalBatch, batch_id)
        assert batch.status == "ready" and batch.lease_generation == 0


async def _seed_page_recovery(
    client: AsyncClient, *, attempts: int = 3, cancelled: bool = False, live_lease: bool = False,
) -> tuple[int, int]:
    """创建关联完整且已同步为 running 的领域 Job 与 ExternalTask。"""

    run_id, _, batch_id = await _seed_external_batch(
        client, suffix="inv3", batch_status="waiting_tasks", task_status="running",
    )
    async with get_session_factory()() as session:
        run = await session.get(AiAgentRun, run_id)
        task = await session.scalar(select(AiAgentExternalTask).where(AiAgentExternalTask.batch_id == batch_id))
        legacy = AiPageMutationBatch(
            batch_id="legacy-inv3", run_id=run_id, session_id=run.session_id, run_step=1, status="pending",
        )
        session.add(legacy)
        await session.flush()
        now = utc_now()
        expires_at = now + timedelta(seconds=300) if live_lease else now - timedelta(seconds=60)
        job = AiPageMutationJob(
            job_id="page-inv3", batch_id=legacy.batch_id, run_id=run_id, session_id=run.session_id,
            tool_call_id=task.tool_call_id, deferred_tool_call_id=task.deferred_tool_call_id,
            operation="create_page", workspace_id=run.workspace_id, status="running",
            worker_id="old-worker", attempt_count=attempts, lease_expires_at=expires_at,
            cancel_requested_at=now if cancelled else None,
        )
        task.worker_id = job.worker_id
        task.lease_expires_at = expires_at
        session.add(job)
        await session.commit()
        return job.id, task.id


@pytest.mark.parametrize("startup", [False, True])
@pytest.mark.parametrize("attempts,cancelled,expected", [(1, False, "pending"), (3, False, "failed"), (3, True, "cancelled")])
async def test_page_recovery_projects_before_returning(
    authenticated_client: AsyncClient, startup: bool, attempts: int, cancelled: bool, expected: str,
) -> None:
    """启动与循环共用恢复入口；返回时已提交的 Job/Task 必须一致，无需协调器对账。"""

    job_id, task_id = await _seed_page_recovery(authenticated_client, attempts=attempts, cancelled=cancelled)
    if startup:
        assert await recover_interrupted_ai_page_mutation_jobs_on_startup(get_session_factory()) == 1
    else:
        async with get_session_factory()() as session:
            # 保留旧 ORM 实体，验证投影读取的是 CAS 后状态。
            stale_job = await session.get(AiPageMutationJob, job_id)
            assert stale_job.status == "running"
            summary = await page_mutation_recovery.recover_page_mutation_jobs(session, max_attempts=3)
            assert summary.total_count == 1
    async with get_session_factory()() as session:
        job = await session.get(AiPageMutationJob, job_id)
        task = await session.get(AiAgentExternalTask, task_id)
        assert job.status == task.status == expected
        assert job.error_code == task.error_code
        assert job.finished_at == task.finished_at
        assert task.worker_id is None and task.lease_expires_at is None
        assert (await audit_cross_table_invariants(session))["inv3"] == []


async def test_page_projection_failure_rolls_back_recovery(
    authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 投影完成后抛错时，两表都必须回滚且可重新恢复。"""

    job_id, task_id = await _seed_page_recovery(authenticated_client)
    finalize = page_mutation_recovery.finalize_external_backed_job

    async def reject_after_projection(session, **kwargs) -> None:
        """注入投影之后的故障，验证事务没有提前提交。"""

        await finalize(session, **kwargs)
        await session.flush()
        raise RuntimeError("投影故障注入")

    with monkeypatch.context() as scoped:
        scoped.setattr(page_mutation_recovery, "finalize_external_backed_job", reject_after_projection)
        async with get_session_factory()() as session:
            with pytest.raises(RuntimeError, match="投影故障注入"):
                await page_mutation_recovery.recover_page_mutation_jobs(session, max_attempts=3)
            # 即使调用方捕获异常再提交，也不能留下半截恢复。
            await session.commit()
    async with get_session_factory()() as session:
        job = await session.get(AiPageMutationJob, job_id)
        task = await session.get(AiAgentExternalTask, task_id)
        assert job.status == task.status == "running"
        assert job.worker_id == task.worker_id == "old-worker"
        assert job.finished_at is None and task.finished_at is None
        assert (await page_mutation_recovery.recover_page_mutation_jobs(session, max_attempts=3)).failed_count == 1


async def test_live_page_lease_should_not_be_projected(
    authenticated_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未过期候选不能触发恢复投影或提前清掉执行者。"""

    await _seed_page_recovery(authenticated_client, live_lease=True)

    async def unexpected(*args, **kwargs) -> None:
        """有效租约若触发投影则立即失败。"""

        pytest.fail("有效租约不得触发恢复投影")

    monkeypatch.setattr(page_mutation_recovery, "finalize_external_backed_job", unexpected)
    async with get_session_factory()() as session:
        assert (await page_mutation_recovery.recover_page_mutation_jobs(session, max_attempts=3)).total_count == 0


@pytest.mark.parametrize("task_status", ["running", "succeeded"])
async def test_inv3_audit_reports_domain_terminal_mismatch(
    authenticated_client: AsyncClient, task_status: str,
) -> None:
    """审计必须识别未同步和终态冲突，不能恒定返回空结果。"""

    job_id, task_id = await _seed_page_recovery(authenticated_client)
    async with get_session_factory()() as session:
        job = await session.get(AiPageMutationJob, job_id)
        task = await session.get(AiAgentExternalTask, task_id)
        job.status = "failed"
        task.status = task_status
        await session.commit()
    async with get_session_factory()() as session:
        audit = await audit_cross_table_invariants(session)
        assert audit["inv3"] == ["page_mutation:page-inv3:AI_INV3_JOB_TASK_MISMATCH"]
        task = await session.get(AiAgentExternalTask, task_id)
        assert task.status == task_status  # 审计只读，不擅自修复。


@pytest.mark.parametrize("domain_status,expected", [
    ("completed", "succeeded"), ("error", "failed"), ("succeeded", "succeeded"), ("failed", "failed"),
])
async def test_inv3_audit_normalizes_image_terminal_aliases(
    authenticated_client: AsyncClient, domain_status: str, expected: str,
) -> None:
    """图片新旧终态均须参与审计，兼容别名不能掩盖真实投影缺口。"""

    run_id, _, batch_id = await _seed_external_batch(
        authenticated_client, suffix="inv3-image", batch_status="waiting_tasks", task_status="running",
    )
    async with get_session_factory()() as session:
        run = await session.get(AiAgentRun, run_id)
        task = await session.scalar(select(AiAgentExternalTask).where(AiAgentExternalTask.batch_id == batch_id))
        task.kind = "image_generation"
        provider = AiImageProviderConfig(user_id=run.user_id, name="审计测试", provider_key="openai_image")
        session.add(provider)
        await session.flush()
        model = AiImageModelConfig(
            user_id=run.user_id, name="审计测试", provider_config_id=provider.id, model_id="test-image",
        )
        session.add(model)
        await session.flush()
        session.add(AiImageGenerationJob(
            job_id="image-inv3", run_id=run_id, session_id=run.session_id, user_id=run.user_id,
            workspace_id=run.workspace_id, model_config_id=model.id, operation="generate",
            tool_call_id=task.tool_call_id, deferred_tool_call_id=task.deferred_tool_call_id, status=domain_status,
        ))
        await session.commit()
        assert (await audit_cross_table_invariants(session))["inv3"] == [
            "image_generation:image-inv3:AI_INV3_JOB_TASK_MISMATCH",
        ]
        task.status = expected
        await session.commit()
        assert (await audit_cross_table_invariants(session))["inv3"] == []
