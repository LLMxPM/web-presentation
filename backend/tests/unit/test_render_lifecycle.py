"""文件功能：用真实双 ORM 会话验证取消/期限/失租结果围栏及截图取消入队竞争。"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.time_utils import utc_now
from app.db.base import Base
from app.models.page_screenshot_job import PageScreenshotJob
from app.models.render_attempt import RenderAttempt
from app.models.render_execution import RenderResult
from app.models.render_request import RenderRequest
from app.services.durable_job_lease_service import request_job_cancellation
from app.services.page_screenshot_render_lifecycle import (
    cancel_screenshot_render_requests,
    screenshot_render_owner_key,
    watch_screenshot_cancellation,
)
from app.services.rendering.coordinator import RenderCoordinator
from app.services.rendering.repository import RenderRepository
from render_contracts.errors import (
    ERROR_CODE_SERVICE_UNAVAILABLE,
    RenderError,
    RenderExecutionError,
)
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.unit


@pytest.fixture
async def sessions(tmp_path):
    """每例使用专属 SQLite 文件，跨会话行为真实执行，不连接开发数据。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'lifecycle.db').as_posix()}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
                RenderRequest.__table__, RenderAttempt.__table__, RenderResult.__table__, PageScreenshotJob.__table__,
            ]))
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def request_fixture(key: str = "owner", *, workspace_id: int = 1) -> RenderRequest:
    """创建未终态截图请求，保持真实必填字段与期限。"""
    return RenderRequest(request_key=key, logical_owner_key=key, business_stage="page.screenshot",
                         operation="page.capture", workspace_id=workspace_id, page_id=7, status="executing",
                         input_digest="input", render_digest="render", request_digest="request",
                         render_profile_digest="profile", deadline_at=utc_now() + timedelta(minutes=1),
                         trace_id="unit", attempt_count=1)


@pytest.mark.parametrize("race", ["cancel", "deadline", "lease", "unreaped-lease", "success"])
async def test_downloaded_result_requires_live_request_and_attempt(sessions, race) -> None:
    """A 下载期间 B 取消/超时/回收租约，A 的真实提交必须整笔回滚且不留孤儿结果。"""
    now = utc_now()
    async with sessions() as seed:
        request = request_fixture()
        seed.add(request)
        await seed.flush()
        attempt = RenderAttempt(request_id=request.id, attempt_uid="race", attempt_no=1, status="running",
                                reserved_at=now, active_occupancy=1, lease_expires_at=now+timedelta(minutes=1))
        seed.add(attempt)
        await seed.commit()
        request_id, attempt_id = request.id, attempt.id
    async with sessions() as downloader:
        request = await downloader.get(RenderRequest, request_id)
        attempt = await downloader.get(RenderAttempt, attempt_id)
        await downloader.commit()
        async with sessions() as rival:
            if race == "cancel":
                await rival.execute(update(RenderRequest).where(RenderRequest.id == request_id).values(cancel_requested=True))
            elif race == "deadline":
                await rival.execute(update(RenderRequest).where(RenderRequest.id == request_id).values(deadline_at=now-timedelta(seconds=1)))
            elif race == "lease":
                await rival.execute(update(RenderAttempt).where(RenderAttempt.id == attempt_id).values(
                    status="terminal", active_occupancy=0, cleanup_status="released", finished_at=now))
            elif race == "unreaped-lease":
                await rival.execute(update(RenderAttempt).where(RenderAttempt.id == attempt_id).values(
                    lease_expires_at=now-timedelta(seconds=1)))
            await rival.commit()
        result = await RenderRepository(downloader).save_result(
            request=request, attempt=attempt, payload={}, object_refs={}, environment_summary={},
            input_digest="input", render_profile_digest="profile", request_digest="request",
        )
        await downloader.commit()
        assert (result is not None) == (race == "success")
    async with sessions() as check:
        assert await check.scalar(select(func.count(RenderResult.id))) == int(race == "success")
        stored = await check.get(RenderAttempt, attempt_id)
        assert stored.active_occupancy == int(race in {"cancel", "deadline", "unreaped-lease"})
        stored_request = await check.get(RenderRequest, request_id)
        assert stored_request.status == ("succeeded" if race == "success" else "executing")
        assert (stored_request.result_id is not None) == (race == "success")


async def test_cancel_before_render_enqueue_is_replayed_without_cross_snapshot_effect(sessions) -> None:
    """取消先提交、请求后入队时 watcher 仍传播；不同空间和视口请求不受影响。"""
    now = utc_now()
    async with sessions() as session:
        job = PageScreenshotJob(page_id=7, workspace_id=1, source="manual", target_page_version_no=1,
                                viewport_width=1920, viewport_height=1080, config_hash="config", status="running",
                                worker_id="owner", cancel_requested_at=now, lease_expires_at=now+timedelta(minutes=1))
        session.add(job)
        await session.commit()
        job_id = job.id
    watcher = asyncio.create_task(watch_screenshot_cancellation(job_id=job_id, worker_id="owner", session_factory=sessions))
    try:
        await asyncio.sleep(0.05)
        key = screenshot_render_owner_key(page_id=7, version_no=1, config_hash="config", width=1920, height=1080)
        async with sessions() as session:
            target, other_workspace, other_viewport = request_fixture(key), request_fixture(key, workspace_id=2), request_fixture(key+"-other")
            # 同一逻辑键的不同 workspace 在实际平台受授权边界限制，本例独立 request_key 避免幂等索引重复。
            other_workspace.request_key = "other-workspace"
            session.add_all([target, other_workspace, other_viewport])
            await session.commit()
            ids = [target.id, other_workspace.id, other_viewport.id]
        async with asyncio.timeout(3):
            while True:
                async with sessions() as check:
                    flags = list(await check.scalars(select(RenderRequest.cancel_requested).where(RenderRequest.id.in_(ids)).order_by(RenderRequest.id)))
                if flags[0]:
                    assert flags == [True, False, False]
                    break
                await asyncio.sleep(0.05)
    finally:
        watcher.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watcher


async def test_unreachable_worker_does_not_renew_attempt_lease() -> None:
    """网络错误不等同于执行存活；不能通过续租阻止持久化过期恢复。"""
    outer = MagicMock()
    outer.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: [(1, "worker", "epoch", "uid")]))
    outer.commit = AsyncMock()
    factory = MagicMock(side_effect=AssertionError("不可达时不应创建续租会话"))
    client = SimpleNamespace(fetch_execution=AsyncMock(side_effect=RenderExecutionError(
        RenderError.from_code(ERROR_CODE_SERVICE_UNAVAILABLE, message="offline", stage="query"))))
    coordinator = RenderCoordinator(session_factory=factory, client=client)
    coordinator._endpoint_for_worker = lambda _: object()
    assert await coordinator._reconcile_running(outer, MagicMock()) == 0
    factory.assert_not_called()


async def test_job_and_render_cancellation_share_rollback_boundary(sessions) -> None:
    """取消传播失败时父 Job 与子 RenderRequest 都回滚，禁止先提交父标记。"""
    now = utc_now()
    key = screenshot_render_owner_key(page_id=7, version_no=1, config_hash="config", width=1920, height=1080)
    async with sessions() as seed:
        job = PageScreenshotJob(page_id=7, workspace_id=1, source="manual", target_page_version_no=1,
                                viewport_width=1920, viewport_height=1080, config_hash="config", status="running",
                                worker_id="owner", lease_expires_at=now+timedelta(minutes=1))
        request = request_fixture(key)
        seed.add_all([job, request])
        await seed.commit()
        job_id, request_id = job.id, request.id
    async with sessions() as cancelling:
        assert await request_job_cancellation(cancelling, PageScreenshotJob, job_id=job_id, commit=False)
        job = await cancelling.get(PageScreenshotJob, job_id)
        assert job.cancel_requested_at is not None
        assert await cancel_screenshot_render_requests(cancelling, job) == 1
        await cancelling.rollback()
    async with sessions() as check:
        assert (await check.get(PageScreenshotJob, job_id)).cancel_requested_at is None
        assert not (await check.get(RenderRequest, request_id)).cancel_requested
