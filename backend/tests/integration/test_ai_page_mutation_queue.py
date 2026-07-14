"""文件功能：验证 AI 页面变更持久化任务的幂等入队、租约认领与取消语义。"""

from __future__ import annotations

import json
from datetime import timedelta

from httpx import AsyncClient
import pytest
from sqlalchemy import select

from app.ai.page_mutation_enqueue import enqueue_page_mutation
from app.ai.page_mutation_executor import AiPageMutationExecutor
from app.ai.page_mutation_queue import (
    _reconcile_cancelled_and_orphaned_jobs,
    _retry_or_fail_job,
    recover_interrupted_ai_page_mutation_jobs_on_startup,
)
from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.ai.run_write_fence import AgentRunWriteFenceLost, PageMutationContinuationWriteFence
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun, AiAgentSession, AiAgentToolCall
from app.models.ai_page_mutation import AiPageMutationBatch, AiPageMutationJob
from app.models.page import Page
from app.models.user import User
from app.schemas.agent import AgentRunEvent
from app.services.durable_job_lease_service import claim_pending_jobs, renew_running_job_lease, request_job_cancellation


async def test_ai_page_mutation_job_should_be_idempotent_and_lease_owned(
    authenticated_client: AsyncClient,
) -> None:
    """同一 run/tool call 重复入队只能生成一个任务，且取消后不能再被领取。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "页面任务队列工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "页面任务队列项目", "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        session.add(
            AiAgentSession(
                session_id="session-page-mutation-1",
                agent_id="agent-coordinator",
                user_id=user.id,
                scope_type="project",
                workspace_id=workspace_id,
                project_id=project_id,
                source="test",
                metadata_json={},
            )
        )
        await session.flush()
        session.add(
            AiAgentRun(
                run_id="run-page-mutation-1",
                session_id="session-page-mutation-1",
                agent_id="agent-coordinator",
                user_id=user.id,
                status="waiting_external",
                scope_type="project",
                workspace_id=workspace_id,
                project_id=project_id,
                source="test",
                input_payload_json={"message": "创建一页"},
                message_history_json=[],
            )
        )
        await session.flush()
        session.add(
            AiAgentToolCall(
                session_id="session-page-mutation-1",
                run_id="run-page-mutation-1",
                tool_call_id="tool-page-mutation-1",
                tool_name="create_project_page",
                status="running",
                input_payload_json={"title": "封面", "page_content": "<template><main /></template>"},
            )
        )
        await session.commit()

    first = await enqueue_page_mutation(
        session_factory,
        run_id="run-page-mutation-1",
        session_id="session-page-mutation-1",
        run_step=2,
        tool_call_id="tool-page-mutation-1",
        operation="create_page",
        workspace_id=workspace_id,
        project_id=project_id,
    )
    duplicate = await enqueue_page_mutation(
        session_factory,
        run_id="run-page-mutation-1",
        session_id="session-page-mutation-1",
        run_step=2,
        tool_call_id="tool-page-mutation-1",
        operation="create_page",
        workspace_id=workspace_id,
        project_id=project_id,
    )

    assert duplicate == first
    async with session_factory() as session:
        jobs = list(
            (
                await session.scalars(
                    select(AiPageMutationJob).where(AiPageMutationJob.run_id == "run-page-mutation-1")
                )
            ).all()
        )
        assert len(jobs) == 1
        claimed = await claim_pending_jobs(
            session,
            AiPageMutationJob,
            worker_id="worker-a",
            limit=1,
            lease_seconds=60,
        )
        assert claimed == [jobs[0].id]

    async with session_factory() as session:
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == first.job_id))
        assert job is not None
        job.lease_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    async with session_factory() as session:
        assert await renew_running_job_lease(
            session,
            AiPageMutationJob,
            job_id=claimed[0],
            worker_id="worker-a",
            lease_seconds=60,
        ) is False

    async with session_factory() as session:
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == first.job_id))
        assert job is not None
        assert job.status == "running"
        assert job.worker_id == "worker-a"
        assert await request_job_cancellation(session, AiPageMutationJob, job_id=job.id) is True

    async with session_factory() as session:
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == first.job_id))
        assert job is not None
        assert job.status == "running"
        assert job.cancel_requested_at is not None

    await _retry_or_fail_job(
        session_factory,
        database_id=claimed[0],
        worker_id="worker-a",
        code="AI_PAGE_MUTATION_EXECUTION_FAILED",
        message="模拟取消后的基础设施错误。",
    )
    async with session_factory() as session:
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == first.job_id))
        assert job is not None
        # 旧 Worker 的租约已经过期，不能借由晚到异常提前释放任务；只能由
        # 过期租约恢复器收敛取消，避免并发新 Worker 与旧 Worker 重叠写入。
        assert job.status == "running"
        assert job.worker_id == "worker-a"

    assert await recover_interrupted_ai_page_mutation_jobs_on_startup(session_factory) == 1
    async with session_factory() as session:
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == first.job_id))
        assert job is not None
        assert job.status == "cancelled"
        assert job.error_code is None

    async with session_factory() as session:
        # 模拟第一轮自动续跑完成；下一次 Pydantic Agent.iter 的 run_step 会重新从零开始。
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == first.job_id))
        assert job is not None
        batch = await session.get(AiPageMutationBatch, first.batch_id)
        run = await session.get(AiAgentRun, "run-page-mutation-1")
        assert batch is not None and run is not None
        batch.status = "completed"
        run.status = "running"
        await session.commit()

    next_round = await enqueue_page_mutation(
        session_factory,
        run_id="run-page-mutation-1",
        session_id="session-page-mutation-1",
        run_step=0,
        tool_call_id="tool-page-mutation-2",
        operation="create_page",
        workspace_id=workspace_id,
        project_id=project_id,
    )
    assert next_round.batch_id != first.batch_id
    async with session_factory() as session:
        first_batch = await session.get(AiPageMutationBatch, first.batch_id)
        next_batch = await session.get(AiPageMutationBatch, next_round.batch_id)
        assert first_batch is not None and next_batch is not None
        assert next_batch.status == "pending"
        assert next_batch.run_step == first_batch.run_step + 1


async def test_expired_continuation_lease_should_restore_waiting_external_run(
    authenticated_client: AsyncClient,
) -> None:
    """续跑进程中断后，过期 Batch 应恢复 run 等待态而不是永久停在 running。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "续跑恢复工作空间", "status": "active"},
    )
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_response.json()["id"], "name": "续跑恢复项目", "status": "active"},
    )
    assert workspace_response.status_code == 200
    assert project_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_id = project_response.json()["id"]
    session_factory = get_session_factory()
    requirement_payload = {
        "id": "requirement-recovery-1",
        "kind": "external_job",
        "run_id": "run-recovery-1",
        "session_id": "session-recovery-1",
        "tool_name": "create_project_page",
        "tool_execution": {"tool_call_id": "tool-recovery-1"},
        "note": "正在后台处理页面变更。",
        "user_feedback_schema": [],
    }

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        session.add(AiAgentSession(
            session_id="session-recovery-1",
            agent_id="agent-coordinator",
            user_id=user.id,
            scope_type="project",
            workspace_id=workspace_id,
            project_id=project_id,
            source="test",
            metadata_json={},
        ))
        await session.flush()
        session.add(AiAgentRun(
            run_id="run-recovery-1",
            session_id="session-recovery-1",
            agent_id="agent-coordinator",
            user_id=user.id,
            status="running",
            scope_type="project",
            workspace_id=workspace_id,
            project_id=project_id,
            source="test",
            input_payload_json={"message": "恢复页面创建"},
            message_history_json=[],
        ))
        await session.flush()
        session.add(AiAgentRequirement(
            requirement_id="requirement-recovery-1",
            session_id="session-recovery-1",
            run_id="run-recovery-1",
            kind="external_job",
            status="resolved",
            tool_call_id="tool-recovery-1",
            tool_name="create_project_page",
            payload_json=requirement_payload,
            resolved_payload_json={"source": "test"},
            resolved_at=utc_now(),
        ))
        session.add(AiPageMutationBatch(
            batch_id="batch-recovery-1",
            run_id="run-recovery-1",
            session_id="session-recovery-1",
            run_step=1,
            status="resuming",
            requirement_id="requirement-recovery-1",
            worker_id="dead-worker",
            lease_expires_at=utc_now() - timedelta(seconds=1),
            heartbeat_at=utc_now() - timedelta(seconds=2),
        ))
        await session.commit()

    assert await recover_interrupted_ai_page_mutation_jobs_on_startup(session_factory) == 1
    async with session_factory() as session:
        run = await session.get(AiAgentRun, "run-recovery-1")
        batch = await session.get(AiPageMutationBatch, "batch-recovery-1")
        assert run is not None and batch is not None
        assert run.status == "waiting_external"
        assert run.pending_requirement_json == requirement_payload
        assert batch.status == "pending"
        assert batch.worker_id is None
        assert batch.lease_generation == 1

    # 恢复会提升代次；过期协调器即使仍持有旧 Session，也不能再追加运行态事件。
    async with session_factory() as session:
        run = await session.get(AiAgentRun, "run-recovery-1")
        assert run is not None
        stale_store = PlatformAgentRuntimeStore(
            session,
            user_id=run.user_id,
            write_fence=PageMutationContinuationWriteFence(
                batch_id="batch-recovery-1",
                worker_id="dead-worker",
                lease_generation=0,
            ),
        )
        with pytest.raises(AgentRunWriteFenceLost):
            await stale_store.append_event(
                run,
                AgentRunEvent(
                    event="run.continued",
                    run_id=run.run_id,
                    session_id=run.session_id,
                ),
            )
        await session.rollback()

    async with session_factory() as session:
        run = await session.get(AiAgentRun, "run-recovery-1")
        assert run is not None
        assert run.event_index == -1


async def test_ai_page_mutation_executor_should_commit_page_and_job_together(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """创建页成功时，页面初始版本和 Job 成功结果应在同一最终事务中写入。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "页面任务执行工作空间", "status": "active"},
    )
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_response.json()["id"], "name": "页面任务执行项目", "status": "active"},
    )
    assert workspace_response.status_code == 200
    assert project_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_id = project_response.json()["id"]
    session_factory = get_session_factory()

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        session.add(AiAgentSession(
            session_id="session-page-mutation-2",
            agent_id="agent-coordinator",
            user_id=user.id,
            scope_type="project",
            workspace_id=workspace_id,
            project_id=project_id,
            source="test",
            metadata_json={},
        ))
        await session.flush()
        run = AiAgentRun(
            run_id="run-page-mutation-2",
            session_id="session-page-mutation-2",
            agent_id="agent-coordinator",
            user_id=user.id,
            status="waiting_external",
            scope_type="project",
            workspace_id=workspace_id,
            project_id=project_id,
            source="test",
            input_payload_json={"message": "创建封面"},
            message_history_json=[],
        )
        session.add(run)
        await session.flush()
        await PlatformAgentRuntimeStore(session, user_id=user.id).append_event(
            run,
            AgentRunEvent(
                event="tool.started",
                run_id=run.run_id,
                session_id=run.session_id,
                data={
                    "tool_call_id": "tool-page-mutation-2",
                    "tool_name": "create_project_page",
                    "tool_args": json.dumps(
                        {
                            "title": "队列封面",
                            "summary": "通过持久化队列创建",
                            "page_content": "<template><main>队列封面</main></template>",
                        },
                        ensure_ascii=False,
                    ),
                },
            ),
        )

    enqueued = await enqueue_page_mutation(
        session_factory,
        run_id="run-page-mutation-2",
        session_id="session-page-mutation-2",
        run_step=1,
        tool_call_id="tool-page-mutation-2",
        operation="create_page",
        workspace_id=workspace_id,
        project_id=project_id,
    )
    async with session_factory() as session:
        claimed = await claim_pending_jobs(
            session,
            AiPageMutationJob,
            worker_id="worker-create",
            limit=1,
            lease_seconds=60,
        )
    assert len(claimed) == 1

    async def fake_check_page_code(self, **kwargs):  # noqa: ANN001
        """替代 Runtime/Chromium，聚焦验证最终数据库原子提交。"""

        _ = self, kwargs
        return {"success": True, "status": "passed", "summary": "代码检查通过。", "diagnostics": []}

    monkeypatch.setattr("app.ai.page_mutation_executor.CodeCheckService.check_page_code", fake_check_page_code)

    phases: list[str] = []

    async def progress(phase: str) -> None:
        """记录 Worker 阶段回调。"""

        phases.append(phase)

    await AiPageMutationExecutor(session_factory).execute(
        database_id=claimed[0],
        worker_id="worker-create",
        progress=progress,
    )

    async with session_factory() as session:
        job = await session.scalar(select(AiPageMutationJob).where(AiPageMutationJob.job_id == enqueued.job_id))
        page = await session.scalar(select(Page).where(Page.project_id == project_id, Page.title == "队列封面"))
        assert job is not None and job.status == "succeeded"
        assert page is not None and page.current_version_no == 1
        assert isinstance(job.result_json, dict) and job.result_json["page_id"] == page.id
    assert phases == ["validating", "saving"]


async def test_reconcile_cancel_should_keep_running_job_and_resuming_batch_lease(
    authenticated_client: AsyncClient,
) -> None:
    """取消和后续孤儿巡检都不能提前释放仍在执行的 Job/Batch 租约。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "页面任务取消租约工作空间", "status": "active"},
    )
    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_response.json()["id"], "name": "页面任务取消租约项目", "status": "active"},
    )
    assert workspace_response.status_code == 200
    assert project_response.status_code == 200
    workspace_id = workspace_response.json()["id"]
    project_id = project_response.json()["id"]
    session_factory = get_session_factory()
    now = utc_now()
    lease_expires_at = now + timedelta(seconds=120)

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        session.add(AiAgentSession(
            session_id="session-page-mutation-cancel-lease",
            agent_id="agent-coordinator",
            user_id=user.id,
            scope_type="project",
            workspace_id=workspace_id,
            project_id=project_id,
            source="test",
            metadata_json={},
        ))
        await session.flush()
        session.add(AiAgentRun(
            run_id="run-page-mutation-cancel-lease",
            session_id="session-page-mutation-cancel-lease",
            agent_id="agent-coordinator",
            user_id=user.id,
            status="cancelling",
            cancel_requested_at=now,
            scope_type="project",
            workspace_id=workspace_id,
            project_id=project_id,
            source="test",
            input_payload_json={"message": "取消页面变更"},
            message_history_json=[],
        ))
        session.add_all([
            AiPageMutationBatch(
                batch_id="batch-page-mutation-cancel-pending",
                run_id="run-page-mutation-cancel-lease",
                session_id="session-page-mutation-cancel-lease",
                run_step=1,
                status="pending",
            ),
            AiPageMutationBatch(
                batch_id="batch-page-mutation-cancel-resuming",
                run_id="run-page-mutation-cancel-lease",
                session_id="session-page-mutation-cancel-lease",
                run_step=2,
                status="resuming",
                worker_id="continuation-owner",
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                lease_generation=1,
            ),
            AiPageMutationJob(
                job_id="job-page-mutation-cancel-pending",
                batch_id="batch-page-mutation-cancel-pending",
                run_id="run-page-mutation-cancel-lease",
                session_id="session-page-mutation-cancel-lease",
                tool_call_id="tool-page-mutation-cancel-pending",
                operation="create_page",
                workspace_id=workspace_id,
                project_id=project_id,
                status="pending",
            ),
            AiPageMutationJob(
                job_id="job-page-mutation-cancel-running",
                batch_id="batch-page-mutation-cancel-resuming",
                run_id="run-page-mutation-cancel-lease",
                session_id="session-page-mutation-cancel-lease",
                tool_call_id="tool-page-mutation-cancel-running",
                operation="create_page",
                workspace_id=workspace_id,
                project_id=project_id,
                status="running",
                attempt_count=1,
                worker_id="job-owner",
                lease_expires_at=lease_expires_at,
                heartbeat_at=now,
                started_at=now,
            ),
        ])
        await session.commit()

    # 首次巡检传播取消；二次巡检覆盖 run 已终态后的孤儿清理分支。
    await _reconcile_cancelled_and_orphaned_jobs(session_factory)
    await _reconcile_cancelled_and_orphaned_jobs(session_factory)

    async with session_factory() as session:
        pending_job = await session.scalar(
            select(AiPageMutationJob).where(AiPageMutationJob.job_id == "job-page-mutation-cancel-pending")
        )
        running_job = await session.scalar(
            select(AiPageMutationJob).where(AiPageMutationJob.job_id == "job-page-mutation-cancel-running")
        )
        pending_batch = await session.get(AiPageMutationBatch, "batch-page-mutation-cancel-pending")
        resuming_batch = await session.get(AiPageMutationBatch, "batch-page-mutation-cancel-resuming")
        run = await session.get(AiAgentRun, "run-page-mutation-cancel-lease")

    assert pending_job is not None and pending_job.status == "cancelled"
    assert pending_batch is not None and pending_batch.status == "cancelled"
    assert running_job is not None
    assert running_job.status == "running"
    assert running_job.cancel_requested_at is not None
    assert running_job.worker_id == "job-owner"
    assert running_job.lease_expires_at is not None
    assert resuming_batch is not None
    assert resuming_batch.status == "resuming"
    assert resuming_batch.worker_id == "continuation-owner"
    assert resuming_batch.lease_expires_at is not None
    assert run is not None and run.status == "cancelled"
