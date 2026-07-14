"""文件功能：验证截图队列关闭时会等待已认领任务安全收敛。"""

from __future__ import annotations

import asyncio

from app.services import page_screenshot_queue_worker as worker


async def test_drain_should_wait_for_registered_screenshot_job_before_browser_pool_shutdown(monkeypatch) -> None:
    """关闭排空不能取消已进入执行链的任务，必须等其真实返回。"""

    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_job(  # noqa: ANN001
        job_id: int,
        *,
        worker_id: str | None = None,
        session_factory=None,
    ) -> None:
        """模拟正在 Chromium 中执行的截图任务。"""

        _ = job_id, worker_id, session_factory
        started.set()
        await release.wait()

    monkeypatch.setattr(worker, "run_page_screenshot_job", blocked_job)
    execution = worker.start_page_screenshot_job_task(42, worker_id="worker-test")
    await started.wait()

    draining = asyncio.create_task(worker.drain_page_screenshot_jobs())
    await asyncio.sleep(0)
    assert not draining.done()

    release.set()
    await execution
    await draining
    assert not worker._ACTIVE_SCREENSHOT_JOB_TASKS
