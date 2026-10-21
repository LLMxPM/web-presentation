"""文件功能：回归 Runtime 时间轴内容错误到 Renderer 诊断/捕获失败的映射及清理。"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from render_contracts.errors import ERROR_CODE_CONTENT_ERROR, RenderExecutionError
from wp_renderer.engine.executor import RenderExecutor
from wp_renderer.engine.render_ready import content_diagnostics_from_ready


def _ready_error() -> dict:
    """构造真实桥接形状的越界海报错误。"""
    return {"ok": False, "contentErrors": [{
        "code": "TIMELINE_SCHEMA_INVALID", "message": "海报时间 3000 毫秒超出 0–2570 毫秒范围。",
        "fieldPath": "timeline.poster.atMs", "trackId": None,
    }]}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["page.diagnose", "page.capture"])
async def test_content_error_fails_validation_or_capture_and_always_cleans_up(tmp_path, operation) -> None:
    """诊断返回 severity=error，捕获拒绝成功图片；两者都必须关闭执行器。"""
    request = SimpleNamespace(
        operation=operation, operation_options={"capture_screenshot": True}, contract_version="v1",
        remaining_budget_ms=10000, deadline_at=(datetime.now(UTC)+timedelta(seconds=20)).isoformat(),
        admission_ticket=None, input_digest="input", render_profile_digest="", request_digest="request",
        request_id="r1", attempt_id="a1", snapshot_ref=SimpleNamespace(artifact_id="rt_1"),
        preview_access=SimpleNamespace(is_expired=lambda:False, navigation_base_url="http://127.0.0.1:7373/__preview"),
    )
    slot = SimpleNamespace(settings=SimpleNamespace(render_profile_digest="",runtime_protocol_version="render-ready.v1"),
        worker_id="worker",worker_epoch="epoch",slot_generation=1,navigations_total=0)
    executor = RenderExecutor(settings=SimpleNamespace(),slot=slot,execution=SimpleNamespace(request=request))
    page = SimpleNamespace(goto=AsyncMock(), evaluate=AsyncMock(return_value=_ready_error()), screenshot=AsyncMock())

    async def launch(_request):
        """只替换浏览器建立，保留 execute 中的就绪、协议映射与终态分支。"""
        executor._page = page
    executor._launch_browser = launch
    executor.shutdown = AsyncMock()
    if operation == "page.diagnose":
        result = await executor.execute(artifact_dir=tmp_path)
        assert result.diagnostics[0].severity == "error"
        assert result.diagnostics[0].code == "TIMELINE_SCHEMA_INVALID"
        assert result.diagnostics[0].evidence["field_path"] == "timeline.poster.atMs"
        assert "2570" in result.diagnostics[0].message
        assert result.screenshot.status == "skipped"
        assert not result.artifacts
    else:
        with pytest.raises(RenderExecutionError) as caught:
            await executor.execute(artifact_dir=tmp_path)
        assert caught.value.error.code == ERROR_CODE_CONTENT_ERROR
        assert caught.value.error.retryable is False
        assert "timeline.poster.atMs" in caught.value.error.message
    page.screenshot.assert_not_awaited()
    executor.shutdown.assert_awaited_once()


def test_content_errors_are_bounded_and_keep_track_location() -> None:
    """不将任意长页面内容带进诊断，同时保留模型准备失败的具体轨道。"""
    ready = {"contentErrors": [{"code":"MODEL_ANIMATION_REFERENCE_STALE","message":"x"*1000,
        "fieldPath":"timeline.tracks.model.clip","trackId":"model"}]*25}
    diagnostics = content_diagnostics_from_ready(ready)
    assert len(diagnostics) == 20
    assert len(diagnostics[0].message) < 600
    assert diagnostics[0].evidence["track_id"] == "model"
    assert content_diagnostics_from_ready({"contentErrors":None}) == []
