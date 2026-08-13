"""文件功能：覆盖统一外部任务协调器的CAS、租约恢复、巡检、补消费与跨Batch推进。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from httpx import AsyncClient
from fastapi import FastAPI
import pytest
from sqlalchemy import select

from app.ai.external_task_queue import (
    _claim_ready_batch,
    _continue_batch,
    _heartbeat_batch,
    audit_external_state_consistency,
    recover_external_continuations,
)
from app.ai.run_write_fence import AgentRunWriteFenceLost, ExternalBatchContinuationWriteFence
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.ai_agent_runtime import AiAgentRequirement, AiAgentRun, AiAgentSession
from app.models.ai_external_task import AiAgentExternalBatch, AiAgentExternalTask
from app.models.user import User


async def _seed_external_batch(
    client: AsyncClient,
    *,
    suffix: str,
    batch_status: str = "ready",
    requirement_status: str = "pending",
    task_status: str = "succeeded",
    result_json: dict | None = None,
    lease_expired: bool = False,
) -> tuple[str, str, str]:
    """创建一个最小但关联完整的waiting_external运行及统一Batch。"""

    response = await client.post("/api/workspaces", json={"name": f"统一协调器-{suffix}", "status": "active"})
    assert response.status_code == 200
    workspace_id = int(response.json()["id"])
    session_id = f"session-external-{suffix}"
    run_id = f"run-external-{suffix}"
    requirement_id = f"requirement-external-{suffix}"
    batch_id = f"batch-external-{suffix}"
    task_id = f"task-external-{suffix}"
    now = utc_now()
    async with get_session_factory()() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        session.add(AiAgentSession(
            session_id=session_id,
            agent_id="agent-coordinator",
            user_id=user.id,
            workspace_id=workspace_id,
            focus_mode="follow_route",
            work_scope_mode="workspace",
            allowed_project_ids_json=[],
            metadata_json={},
        ))
        await session.flush()
        session.add(AiAgentRun(
            run_id=run_id,
            session_id=session_id,
            agent_id="agent-coordinator",
            user_id=user.id,
            status="waiting_external",
            scope_type="workspace",
            workspace_id=workspace_id,
            source="test",
            input_payload_json={"message": "测试统一续跑"},
            message_history_json=[],
            pending_requirement_json={"id": requirement_id, "kind": "external_job"},
            updated_at=now - timedelta(minutes=1),
        ))
        await session.flush()
        session.add(AiAgentRequirement(
            requirement_id=requirement_id,
            session_id=session_id,
            run_id=run_id,
            kind="external_job",
            status=requirement_status,
            tool_call_id=f"tool-{suffix}",
            tool_name="create_entity",
            payload_json={"tool_execution": {"tool_calls": []}},
            resolved_at=now if requirement_status == "resolved" else None,
        ))
        session.add(AiAgentExternalBatch(
            batch_id=batch_id,
            run_id=run_id,
            session_id=session_id,
            requirement_id=requirement_id,
            sequence_no=1,
            status=batch_status,
            worker_id="expired-worker" if batch_status == "resuming" else None,
            lease_generation=3 if batch_status == "resuming" else 0,
            lease_expires_at=(now - timedelta(seconds=1)) if lease_expired else None,
            heartbeat_at=(now - timedelta(minutes=1)) if batch_status == "resuming" else None,
        ))
        await session.flush()
        session.add(AiAgentExternalTask(
            task_id=task_id,
            batch_id=batch_id,
            run_id=run_id,
            session_id=session_id,
            kind="page_mutation",
            tool_call_id=f"tool-{suffix}",
            deferred_tool_call_id=f"raw-{suffix}",
            status=task_status,
            result_json=result_json,
            finished_at=now if task_status in {"succeeded", "failed", "cancelled"} else None,
        ))
        await session.commit()
    return run_id, requirement_id, batch_id


async def test_ready_batch_cas_should_allow_only_one_coordinator(authenticated_client: AsyncClient) -> None:
    """两个协调器并发认领同一Batch时只能一个成功。"""

    _, requirement_id, batch_id = await _seed_external_batch(authenticated_client, suffix="cas")
    results = await asyncio.gather(
        _claim_ready_batch(get_session_factory(), worker_id="coordinator-a"),
        _claim_ready_batch(get_session_factory(), worker_id="coordinator-b"),
    )

    assert sum(item is not None for item in results) == 1
    assert next(item for item in results if item is not None)[0] == batch_id
    async with get_session_factory()() as session:
        batch = await session.get(AiAgentExternalBatch, batch_id)
        requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == requirement_id)
        )
        assert batch is not None and batch.status == "resuming" and batch.lease_generation == 1
        assert requirement is not None and requirement.status == "resolving"


async def test_expired_resuming_batch_should_restore_ready_and_requirement_pending(
    authenticated_client: AsyncClient,
) -> None:
    """过期续跑租约必须增加代次，并把Requirement从resolving恢复pending。"""

    _, requirement_id, batch_id = await _seed_external_batch(
        authenticated_client,
        suffix="recover",
        batch_status="resuming",
        requirement_status="resolving",
        lease_expired=True,
    )
    await recover_external_continuations(get_session_factory())

    async with get_session_factory()() as session:
        batch = await session.get(AiAgentExternalBatch, batch_id)
        requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == requirement_id)
        )
        assert batch is not None and batch.status == "ready" and batch.lease_generation == 4
        assert batch.worker_id is None and batch.lease_expires_at is None
        assert requirement is not None and requirement.status == "pending"


async def test_expired_resuming_batch_with_resolved_requirement_should_finish_consumption(
    authenticated_client: AsyncClient,
) -> None:
    """模型历史已提交但收尾丢失时应补消费，不能再次续跑。"""

    _, _, batch_id = await _seed_external_batch(
        authenticated_client,
        suffix="consume",
        batch_status="resuming",
        requirement_status="resolved",
        result_json={"success": True, "page_id": 8, "diagnostics": "large"},
        lease_expired=True,
    )
    await recover_external_continuations(get_session_factory())

    async with get_session_factory()() as session:
        batch = await session.get(AiAgentExternalBatch, batch_id)
        task = await session.scalar(select(AiAgentExternalTask).where(AiAgentExternalTask.batch_id == batch_id))
        assert batch is not None and batch.status == "completed"
        assert task is not None and task.result_json is None and task.result_consumed_at is not None
        assert task.result_summary_json["page_id"] == 8


async def test_waiting_external_orphan_should_fail_consistency_audit(authenticated_client: AsyncClient) -> None:
    """超过grace且缺少Requirement的waiting_external Run必须确定失败。"""

    run_id, requirement_id, batch_id = await _seed_external_batch(authenticated_client, suffix="orphan")
    async with get_session_factory()() as session:
        requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == requirement_id)
        )
        await session.delete(requirement)
        await session.commit()
    await audit_external_state_consistency(get_session_factory())

    async with get_session_factory()() as session:
        run = await session.get(AiAgentRun, run_id)
        assert run is not None and run.status == "failed"
        assert run.error_code == "AI_EXTERNAL_STATE_INCONSISTENT"


async def test_stale_continuation_fence_should_reject_late_write(authenticated_client: AsyncClient) -> None:
    """Batch被新协调器认领后，旧租约代次不得继续写入。"""

    _, _, batch_id = await _seed_external_batch(authenticated_client, suffix="fence")
    claimed = await _claim_ready_batch(get_session_factory(), worker_id="new-owner")
    assert claimed == (batch_id, 1)
    stale = ExternalBatchContinuationWriteFence(batch_id=batch_id, worker_id="old-owner", lease_generation=0)
    async with get_session_factory()() as session:
        with pytest.raises(AgentRunWriteFenceLost):
            await stale.ensure_owned(session, now=utc_now())


async def test_completed_old_batch_should_not_block_next_batch_claim(authenticated_client: AsyncClient) -> None:
    """旧Batch完成后，同一Run的新外部阶段仍应被统一协调器认领。"""

    run_id, old_requirement_id, old_batch_id = await _seed_external_batch(authenticated_client, suffix="next")
    assert await _claim_ready_batch(get_session_factory(), worker_id="first-owner") == (old_batch_id, 1)
    async with get_session_factory()() as session:
        old_batch = await session.get(AiAgentExternalBatch, old_batch_id)
        old_requirement = await session.scalar(
            select(AiAgentRequirement).where(AiAgentRequirement.requirement_id == old_requirement_id)
        )
        assert old_batch is not None and old_requirement is not None
        old_batch.status = "completed"
        old_requirement.status = "resolved"
        new_requirement_id = "requirement-external-next-2"
        session.add(AiAgentRequirement(
            requirement_id=new_requirement_id,
            session_id=old_batch.session_id,
            run_id=run_id,
            kind="external_job",
            status="pending",
            tool_call_id="tool-next-2",
            tool_name="generate_image",
            payload_json={},
        ))
        session.add(AiAgentExternalBatch(
            batch_id="batch-external-next-2",
            run_id=run_id,
            session_id=old_batch.session_id,
            requirement_id=new_requirement_id,
            sequence_no=2,
            status="ready",
        ))
        await session.flush()
        session.add(AiAgentExternalTask(
            task_id="task-external-next-2",
            batch_id="batch-external-next-2",
            run_id=run_id,
            session_id=old_batch.session_id,
            kind="image_generation",
            tool_call_id="tool-next-2",
            deferred_tool_call_id="raw-next-2",
            status="succeeded",
            result_json={"success": True},
            finished_at=utc_now(),
        ))
        await session.commit()

    assert await _claim_ready_batch(get_session_factory(), worker_id="second-owner") == (
        "batch-external-next-2",
        1,
    )


async def test_batch_heartbeat_loss_should_signal_continuation_cancel(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """续租CAS失败必须设置lease_lost，供协调器主动取消模型调用。"""

    _, _, batch_id = await _seed_external_batch(authenticated_client, suffix="heartbeat")
    monkeypatch.setattr(
        "app.ai.external_task_queue.get_settings",
        lambda: SimpleNamespace(durable_job_heartbeat_seconds=1, durable_job_lease_seconds=3),
    )
    lease_lost = asyncio.Event()
    stale = ExternalBatchContinuationWriteFence(batch_id=batch_id, worker_id="nobody", lease_generation=99)
    heartbeat = asyncio.create_task(
        _heartbeat_batch(get_session_factory(), fence=stale, lease_lost=lease_lost)
    )
    await asyncio.wait_for(lease_lost.wait(), timeout=2)
    await heartbeat
    assert lease_lost.is_set()


async def test_heartbeat_loss_should_actively_cancel_model_continuation(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """心跳报告租约丢失后，协调器应立即取消尚未完成的模型调用。"""

    _, _, batch_id = await _seed_external_batch(authenticated_client, suffix="cancel-model")
    claimed = await _claim_ready_batch(get_session_factory(), worker_id="cancel-owner")
    assert claimed == (batch_id, 1)
    model_started = asyncio.Event()
    model_cancelled = asyncio.Event()

    async def fake_heartbeat(session_factory, *, fence, lease_lost):
        _ = session_factory, fence
        await model_started.wait()
        lease_lost.set()

    async def fake_continue(self, **kwargs):
        _ = self, kwargs
        model_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            model_cancelled.set()
            raise

    monkeypatch.setattr("app.ai.external_task_queue._heartbeat_batch", fake_heartbeat)
    monkeypatch.setattr(
        "app.ai.external_task_queue.AgentSessionFacade.continue_external_job_to_store",
        fake_continue,
    )

    await asyncio.wait_for(
        _continue_batch(
            get_session_factory(),
            app=FastAPI(),
            batch_id=batch_id,
            worker_id="cancel-owner",
            lease_generation=1,
        ),
        timeout=2,
    )

    assert model_cancelled.is_set()
