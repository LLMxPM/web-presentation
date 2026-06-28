"""文件功能：验证 Backend Playwright 任务队列的跨服务并发限制。"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from app.core.config import AppSettings
from app.services.browser_capture_service import BrowserCaptureService
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.page_render_diagnostics_service import PageRenderDiagnosticsService
from app.services.playwright_task_queue import PlaywrightTaskQueue


async def test_playwright_task_queue_should_limit_capture_and_diagnostics_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """页面截图和渲染诊断共享队列时，应受同一并发上限约束。"""

    queue = PlaywrightTaskQueue(concurrency=1)
    capture_service = BrowserCaptureService(playwright_task_queue=queue)
    diagnostics_service = PageRenderDiagnosticsService(playwright_task_queue=queue)
    viewport = CaptureViewport(width=1280, height=720)
    lock = threading.Lock()
    active_count = 0
    max_active_count = 0

    def blocking_result(value: Any) -> Any:
        """模拟同步 Playwright 任务，并记录线程池内同时执行数量。"""

        nonlocal active_count, max_active_count
        with lock:
            active_count += 1
            max_active_count = max(max_active_count, active_count)
        try:
            time.sleep(0.05)
            return value
        finally:
            with lock:
                active_count -= 1

    def fake_capture_preview_sync(
        preview_url: str,
        viewport: CaptureViewport,
        extra_http_headers: dict[str, str] | None = None,
    ) -> bytes:
        """替代真实截图，避免单元测试启动浏览器。"""

        _ = preview_url, viewport, extra_http_headers
        return blocking_result(b"capture")

    def fake_diagnose_preview_sync(preview_url: str, viewport: CaptureViewport) -> list[dict[str, object]]:
        """替代真实渲染诊断，避免单元测试启动浏览器。"""

        _ = preview_url, viewport
        return blocking_result([{"severity": "warning", "code": "TEST"}])

    monkeypatch.setattr(capture_service, "_capture_preview_sync", fake_capture_preview_sync)
    monkeypatch.setattr(diagnostics_service, "_diagnose_preview_sync", fake_diagnose_preview_sync)

    capture_result, diagnostics_result = await asyncio.gather(
        capture_service.capture_preview("http://127.0.0.1:7373/__preview", viewport),
        diagnostics_service.diagnose_preview("http://127.0.0.1:7373/__preview", viewport),
    )

    assert capture_result == b"capture"
    assert diagnostics_result == [{"severity": "warning", "code": "TEST"}]
    assert max_active_count == 1


def test_playwright_task_concurrency_should_be_positive() -> None:
    """Playwright 统一并发配置必须为正整数。"""

    assert AppSettings(_env_file=None).playwright_task_concurrency == 1
    with pytest.raises(ValueError, match="Playwright"):
        AppSettings(_env_file=None, playwright_task_concurrency=0)
