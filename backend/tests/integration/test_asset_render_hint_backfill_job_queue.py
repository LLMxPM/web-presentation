"""文件功能：验证资源比例回填任务的数据库领取、attempt 围栏与超时租约恢复语义。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.asset_render_hint_backfill_job import AssetRenderHintBackfillJob
from app.services.asset_render_hint_backfill_job_service import (
    MAX_BACKFILL_JOB_ATTEMPTS,
    AssetRenderHintBackfillJobService,
    run_asset_render_hint_backfill_job,
)
from app.services.asset_render_metadata_service import AssetRenderMetadataService
from app.services.durable_job_lease_service import build_durable_worker_id


NEXT_METADATA = AssetRenderMetadataService.build_metadata_from_ratio(2.0, source="auto")


async def _expire_lease(session: AsyncSession, job_id: int) -> None:
    """把任务租约推到过去，模拟执行者卡死或进程退出。"""

    await session.execute(
        update(AssetRenderHintBackfillJob)
        .where(AssetRenderHintBackfillJob.id == job_id)
        .values(lease_expires_at=utc_now() - timedelta(seconds=1))
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def _create_single_job(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str = "preview",
) -> tuple[int, int, int]:
    """创建一个只含单个任务的回填任务组，返回任务、资源与工作空间 ID。"""

    async def fake_measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any]:  # noqa: ARG001
        """返回固定测量结果，避免测试依赖 Runtime。"""

        return dict(NEXT_METADATA)

    monkeypatch.setattr(
        "app.services.asset_render_hint_measurement_service.AssetRenderHintMeasurementService.measure_metadata",
        fake_measure_metadata,
    )
    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": f"回填租约空间-{mode}", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = int(workspace_response.json()["id"])
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "formula",
            "name": f"lease_{mode}",
            "original_name": f"lease_{mode}.tex",
            "content": "E = mc^2",
            "tags": [],
        },
    )
    assert asset_response.status_code == 200
    asset_id = int(asset_response.json()["id"])
    group_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/render-hint-backfill-jobs",
        json={"asset_types": ["formula"], "asset_ids": [asset_id], "mode": mode},
    )
    assert group_response.status_code == 200
    group = group_response.json()
    jog_response = await authenticated_client.get(
        f"/api/asset-render-hint-backfill-job-groups/{group['job_group_id']}",
    )
    assert jog_response.status_code == 200
    job_id = int(jog_response.json()["jobs"][0]["id"])
    return job_id, asset_id, workspace_id


async def _read_job(job_id: int) -> AssetRenderHintBackfillJob:
    """在独立会话中读取任务当前状态。"""

    async with get_session_factory()() as session:
        return await AssetRenderHintBackfillJobService(session).get_job_by_id(job_id)


async def _read_asset_metadata(workspace_id: int, asset_id: int) -> dict[str, Any] | None:
    """在独立会话中读取资源当前的 render_metadata。"""

    async with get_session_factory()() as session:
        asset = await AssetRenderHintBackfillJobService(session).asset_service._get_asset_or_raise(
            workspace_id, asset_id
        )
        return asset.render_metadata


@pytest.mark.asyncio
async def test_claim_should_rely_on_database_condition_only(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """领取只依赖数据库条件更新：落后候选无法二次领取，运行态被禁用也照常工作。"""

    job_id, _, _ = await _create_single_job(authenticated_client, monkeypatch)
    factory = get_session_factory()
    worker_a = build_durable_worker_id()
    worker_b = build_durable_worker_id()

    # 运行态存储整体不可用时，领取与执行准备仍必须成立。
    def _runtime_state_disabled() -> None:
        raise AssertionError("资源比例回填任务不得依赖运行态存储")

    monkeypatch.setattr(
        "app.services.redis_runtime_client.get_redis_runtime_client",
        _runtime_state_disabled,
    )

    async with factory() as session_a, factory() as session_b:
        claimed_a = await AssetRenderHintBackfillJobService(session_a).claim_pending_jobs(
            limit=5, worker_id=worker_a
        )
        assert [job.id for job in claimed_a] == [job_id]
        # 第二个领取者即使持有领取前的 candidates，也只能得到 0 行更新。
        stale = await session_b.execute(
            update(AssetRenderHintBackfillJob)
            .where(
                AssetRenderHintBackfillJob.id == job_id,
                AssetRenderHintBackfillJob.status == "pending",
            )
            .values(status="running", worker_id=worker_b)
            .execution_options(synchronize_session=False)
        )
        await session_b.commit()
        assert (stale.rowcount or 0) == 0
        claimed_b = await AssetRenderHintBackfillJobService(session_b).claim_pending_jobs(
            limit=5, worker_id=worker_b
        )
        assert claimed_b == []

    job = await _read_job(job_id)
    assert job.status == "running"
    assert job.worker_id == worker_a
    assert job.attempt_count == 1
    assert job.lease_expires_at is not None
    assert job.heartbeat_at is not None


@pytest.mark.asyncio
async def test_concurrent_claims_should_elect_single_winner(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个并发领取者对同一批 pending 任务最多一个成功。"""

    job_id, _, _ = await _create_single_job(authenticated_client, monkeypatch)
    factory = get_session_factory()
    worker_a = build_durable_worker_id()
    worker_b = build_durable_worker_id()

    async def _claim(worker_id: str) -> list[int]:
        async with factory() as session:
            claimed = await AssetRenderHintBackfillJobService(session).claim_pending_jobs(
                limit=5, worker_id=worker_id
            )
            return [job.id for job in claimed]

    first, second = await asyncio.gather(_claim(worker_a), _claim(worker_b))

    assert sorted(first + second) == [job_id]
    job = await _read_job(job_id)
    assert job.status == "running"
    assert job.attempt_count == 1


@pytest.mark.asyncio
async def test_stale_attempt_result_should_be_rejected_after_new_attempt_claims(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧 attempt 的迟到成功不能覆盖新 attempt，也不能写入资源元数据。"""

    job_id, asset_id, workspace_id = await _create_single_job(authenticated_client, monkeypatch, mode="apply")
    factory = get_session_factory()
    worker_a = build_durable_worker_id()
    worker_b = build_durable_worker_id()

    async with factory() as session:
        claimed_a = await AssetRenderHintBackfillJobService(session).claim_pending_jobs(
            limit=5, worker_id=worker_a
        )
    assert [job.id for job in claimed_a] == [job_id]

    class _TakeoverMeasurementService:
        """在旧 attempt 测量期间让租约过期并由新 attempt 接管。"""

        async def measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any] | None:  # noqa: ARG002
            async with get_session_factory()() as session:
                await _expire_lease(session, job_id)
                service = AssetRenderHintBackfillJobService(session)
                await service.recover_interrupted_jobs()
                claimed = await service.claim_pending_jobs(limit=5, worker_id=worker_b)
                assert [job.id for job in claimed] == [job_id]
            return dict(NEXT_METADATA)

    async with factory() as session:
        service = AssetRenderHintBackfillJobService(session, measurement_service=_TakeoverMeasurementService())
        await service.run_claimed_job(job_id, worker_id=worker_a)

    job = await _read_job(job_id)
    assert job.status == "running"
    assert job.worker_id == worker_b
    assert job.attempt_count == 2
    assert job.error_code is None
    assert job.finished_at is None
    assert await _read_asset_metadata(workspace_id, asset_id) is None

    await run_asset_render_hint_backfill_job(job_id, worker_id=worker_b, session_factory=factory)

    job = await _read_job(job_id)
    assert job.status == "succeeded"
    assert job.finished_at is not None
    assert job.lease_expires_at is None
    assert job.next_render_metadata == NEXT_METADATA
    assert await _read_asset_metadata(workspace_id, asset_id) == NEXT_METADATA


@pytest.mark.asyncio
async def test_expired_lease_attempt_should_not_commit_and_should_be_requeued(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """领取后进程退出：旧 attempt 无法提交，任务按重试预算回到 pending 并可再次成功。"""

    job_id, asset_id, workspace_id = await _create_single_job(authenticated_client, monkeypatch, mode="apply")
    factory = get_session_factory()
    worker_a = build_durable_worker_id()
    worker_b = build_durable_worker_id()

    async with factory() as session:
        claimed = await AssetRenderHintBackfillJobService(session).claim_pending_jobs(
            limit=5, worker_id=worker_a
        )
        await _expire_lease(session, job_id)
    assert [job.id for job in claimed] == [job_id]

    await run_asset_render_hint_backfill_job(job_id, worker_id=worker_a, session_factory=factory)

    job = await _read_job(job_id)
    assert job.status == "running"
    assert job.error_code is None
    assert await _read_asset_metadata(workspace_id, asset_id) is None

    async with factory() as session:
        service = AssetRenderHintBackfillJobService(session)
        assert await service.recover_interrupted_jobs() == 1
        claimed_b = await service.claim_pending_jobs(limit=5, worker_id=worker_b)
    assert [job.id for job in claimed_b] == [job_id]

    await run_asset_render_hint_backfill_job(job_id, worker_id=worker_b, session_factory=factory)

    job = await _read_job(job_id)
    assert job.status == "succeeded"
    assert job.attempt_count == 2
    assert await _read_asset_metadata(workspace_id, asset_id) == NEXT_METADATA


@pytest.mark.asyncio
async def test_recovery_should_fail_job_after_retry_budget_exhausted(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """租约过期且重试预算耗尽的 running 任务必须收敛为可解释的失败。"""

    job_id, _, _ = await _create_single_job(authenticated_client, monkeypatch)
    factory = get_session_factory()

    async with factory() as session:
        await session.execute(
            update(AssetRenderHintBackfillJob)
            .where(AssetRenderHintBackfillJob.id == job_id)
            .values(
                status="running",
                attempt_count=MAX_BACKFILL_JOB_ATTEMPTS,
                worker_id=build_durable_worker_id(),
                lease_expires_at=utc_now() - timedelta(seconds=1),
            )
            .execution_options(synchronize_session=False)
        )
        await session.commit()

    async with factory() as session:
        assert await AssetRenderHintBackfillJobService(session).recover_interrupted_jobs() == 1

    job = await _read_job(job_id)
    assert job.status == "failed"
    assert job.error_code == "ASSET_RENDER_HINT_BACKFILL_JOB_INTERRUPTED"
    assert job.lease_expires_at is None
    assert job.finished_at is not None