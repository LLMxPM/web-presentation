"""文件功能：验证远程渲染截图业务入口的错误契约与批量结果结构。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppException
from app.services.browser_capture_service import BrowserCaptureJob, BrowserCaptureService
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.page_render_diagnostics_service import (
    PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE,
    PageRenderDiagnosticsService,
)
from app.services.rendering.errors import render_error_to_app_exception
from render_contracts.errors import ERROR_CODE_QUEUE_FULL, RenderError

pytestmark = pytest.mark.unit


def test_render_error_maps_to_app_exception_with_trace() -> None:
    """渲染错误应映射为统一 AppException，并携带 trace_id。"""

    error = RenderError.from_code(
        ERROR_CODE_QUEUE_FULL,
        message="渲染队列已满。",
        stage="enqueue",
        trace_id="trace-1",
    )
    exc = render_error_to_app_exception(error)
    assert isinstance(exc, AppException)
    assert exc.code == ERROR_CODE_QUEUE_FULL
    assert exc.status_code == 429
    assert "trace-1" in exc.detail


@pytest.mark.asyncio
async def test_browser_capture_batch_keeps_per_item_failures(monkeypatch) -> None:
    """批量截图应保留逐项失败，不把单页失败吞成整批失败。"""

    async def fake_capture(self, preview_url, viewport, **kwargs):  # noqa: ANN001, ARG001
        if "bad" in preview_url:
            raise AppException(status_code=503, code="RENDER_SERVICE_UNAVAILABLE", detail="执行不可用")
        return b"PNG"

    monkeypatch.setattr(BrowserCaptureService, "capture_preview", fake_capture)
    service = BrowserCaptureService()
    jobs = [
        BrowserCaptureJob(key=1, preview_url="http://ok", viewport=CaptureViewport(width=10, height=10)),
        BrowserCaptureJob(key=2, preview_url="http://bad", viewport=CaptureViewport(width=10, height=10)),
    ]
    results = await service.capture_preview_batch(jobs)
    assert results[0].content == b"PNG"
    assert results[1].content is None
    assert isinstance(results[1].error, AppException)
    assert results[1].error.code == "RENDER_SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_page_diagnostics_unavailable_is_infrastructure_not_content_error(monkeypatch) -> None:
    """页面诊断执行不可用不能映射为源码有错。"""

    async def fake_diagnose(self, preview_url, viewport, **kwargs):  # noqa: ANN001, ARG001
        raise AppException(status_code=503, code="RENDER_SERVICE_UNAVAILABLE", detail="Renderer 离线")

    monkeypatch.setattr(PageRenderDiagnosticsService, "diagnose_preview", fake_diagnose)
    # 直接验证不可用结果构造
    result = PageRenderDiagnosticsService._build_unavailable_result("Renderer 离线")
    assert result["status"] == "unavailable"
    diagnostics = result["diagnostics"]
    assert diagnostics[0]["code"] == PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE
    assert diagnostics[0]["source"] == "infrastructure"


@pytest.mark.asyncio
async def test_capture_preview_batch_uses_independent_facade(monkeypatch) -> None:
    """批量截图不得复用 self.facade 的共享 AsyncSession。"""

    from app.services.rendering.domain_facade import RenderDomainFacade

    seen: list[object] = []

    async def fake_capture(self, preview_url, viewport, **kwargs):  # noqa: ANN001, ARG001
        seen.append(kwargs.get("facade"))
        return b"PNG"

    monkeypatch.setattr(BrowserCaptureService, "capture_preview", fake_capture)
    shared = RenderDomainFacade(None)
    service = BrowserCaptureService(facade=shared)
    jobs = [
        BrowserCaptureJob(key=1, preview_url="http://a", viewport=CaptureViewport(width=10, height=10)),
        BrowserCaptureJob(key=2, preview_url="http://b", viewport=CaptureViewport(width=10, height=10)),
    ]
    results = await service.capture_preview_batch(jobs)
    assert len(results) == 2
    assert all(item is not None for item in seen)
    assert all(item is not shared for item in seen)
    assert seen[0] is not seen[1]
