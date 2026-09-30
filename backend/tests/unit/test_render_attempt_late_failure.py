"""文件功能：用真实 ORM 会话验证迟到失败不会覆盖另一协调器已保存的渲染终态。"""

from datetime import timedelta

import pytest
from app.core.time_utils import utc_now
from app.db.base import Base
from app.models.render_attempt import RenderAttempt
from app.models.render_request import RenderRequest
from app.services.rendering.repository import RenderRepository
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("release_slot", [False, True])
async def test_late_artifact_failure_preserves_committed_result(tmp_path, release_slot: bool) -> None:
    """A 先读运行态，B 提交成功并消费产物，A 遇到 410 后提交不能污染已释放的 attempt。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'render-race.db').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: Base.metadata.create_all(sync, tables=[RenderRequest.__table__, RenderAttempt.__table__])
            )
        now = utc_now()
        async with sessions() as session:
            request = RenderRequest(
                request_key="key", logical_owner_key="page-screenshot:race", business_stage="page.screenshot",
                operation="page.capture", workspace_id=1, status="executing", input_digest="input",
                render_digest="render", request_digest="request", render_profile_digest="profile",
                deadline_at=now + timedelta(minutes=1), trace_id="race", attempt_count=1,
            )
            session.add(request)
            await session.flush()
            attempt = RenderAttempt(
                request_id=request.id, attempt_uid="race-attempt", attempt_no=1,
                status="running", reserved_at=now, active_occupancy=1,
            )
            session.add(attempt)
            await session.commit()
            request_id, attempt_id = request.id, attempt.id
        async with sessions() as late_session:
            request = await late_session.get(RenderRequest, request_id)
            attempt = await late_session.get(RenderAttempt, attempt_id)
            await late_session.commit()
            async with sessions() as winner:
                await winner.execute(update(RenderAttempt).where(RenderAttempt.id == attempt_id).values(
                    status="terminal", active_occupancy=0, cleanup_status="released", cleaned_at=now, finished_at=now,
                ))
                await winner.execute(update(RenderRequest).where(RenderRequest.id == request_id).values(
                    status="succeeded", result_id=42, finished_at=now,
                ))
                await winner.commit()
            await RenderRepository(late_session).fail_attempt(
                request=request, attempt=attempt, error_code="RENDER_SERVICE_UNAVAILABLE",
                error_message="Renderer 产物 HTTP 410。", retryable=True, retry_after=now,
                release_slot=release_slot, terminal=False,
            )
            await late_session.commit()
        async with sessions() as check:
            stored_attempt = await check.get(RenderAttempt, attempt_id)
            stored_request = await check.get(RenderRequest, request_id)
            assert (stored_attempt.status, stored_attempt.cleanup_status, stored_attempt.active_occupancy) == (
                "terminal", "released", 0,
            )
            assert stored_attempt.error_code is None and stored_attempt.error_message is None
            assert (stored_request.status, stored_request.result_id) == ("succeeded", 42)
            assert stored_request.error_code is None
    finally:
        await engine.dispose()
