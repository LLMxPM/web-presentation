"""文件功能：验证独立静态回执的捕获准入和不可呈现对布局诊断的隔离。"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from render_contracts.errors import RenderExecutionError
from render_contracts.schema import ExecutionResult
from wp_renderer.engine.joint_capture import append_screenshot
from wp_renderer.engine.static_presentation import require_static_presentation


@pytest.mark.parametrize("status,code,retryable", [
    ("unsupported", "STATIC_PRESENTATION_UNAVAILABLE", False),
    ("failed", "RENDER_ASSET_NOT_READY", True),
    (None, "RENDER_CONTRACT_MISMATCH", False),
])
def test_capture_requires_explicit_static_receipt(status, code, retryable):
    """未知或缺失回执不允许捕获，不可呈现与资源失败分开。"""
    bridge = {"staticPresentation": {"status": status, "message": "静态原因"}} if status else {}
    with pytest.raises(RenderExecutionError) as caught:
        require_static_presentation(bridge)
    assert caught.value.error.code == code
    assert caught.value.error.retryable is retryable
    require_static_presentation({"staticPresentation": {"status": "ready"}})


@pytest.mark.asyncio
async def test_unavailable_image_preserves_successful_layout(tmp_path: Path):
    """布局已完成后图片不可呈现，保留布局且不发起截图，也不把它当作可重试失败。"""
    result = ExecutionResult("r", "a", "w", "e", 1, "page.diagnose", "i", "p", "d", "render-result.v1", {}, layout={"nodes": 1})
    executor = SimpleNamespace(
        execution=SimpleNamespace(request=SimpleNamespace(operation_options={"capture_screenshot": True}, attempt_id="a")),
        _deadline=SimpleNamespace(remaining_seconds=lambda: 5), _check_cancel=lambda **kw: None,
        _capture_page=AsyncMock(),
    )

    async def prepare(*args, **kwargs):
        """保留真实准入错误，替换浏览器调用。"""
        require_static_presentation({"staticPresentation": {"status": "unsupported"}})

    async def bounded(coro, **kwargs):
        """直接等待图片流程，复用真实异常隔离逻辑。"""
        return await coro

    executor._prepare_static_capture = prepare
    executor._await_without_cancelling = bounded
    actual = await append_screenshot(executor, result, ready={}, artifact_dir=tmp_path)
    assert actual.layout == result.layout
    assert actual.screenshot.status == "unavailable"
    assert actual.screenshot.reason_code == "STATIC_PRESENTATION_UNAVAILABLE"
    assert actual.screenshot.retryable is False
    executor._capture_page.assert_not_awaited()
