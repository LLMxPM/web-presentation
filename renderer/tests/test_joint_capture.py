"""文件功能：验证诊断后附带截图的顺序、独立失败与硬期限语义。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from render_contracts.schema import ExecutionResult

from wp_renderer.engine.joint_capture import append_screenshot


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_joint_capture_preserves_layout_and_reuses_executor(failure, tmp_path: Path):
    """已产出的布局不会被图片错误覆盖，捕获仅操作现有执行器。"""
    result = ExecutionResult("r", "a", "w", "e", 1, "page.diagnose", "i", "p", "d", "render-result.v1", {}, layout={"nodes": 1})
    executor = SimpleNamespace(execution=SimpleNamespace(request=SimpleNamespace(operation_options={"capture_screenshot": True}, attempt_id="a")),
                               _deadline=SimpleNamespace(remaining_seconds=lambda: 5), _check_cancel=lambda **kw: None,
                               _prepare_static_capture=AsyncMock(), _capture_page=AsyncMock(return_value=result))

    async def bounded(coro, *, timeout):
        """执行受限图片流程，并可模拟编码失败。"""
        await coro
        if failure:
            raise RuntimeError("PNG encode failed")
        return result

    executor._await_without_cancelling = bounded
    actual = await append_screenshot(executor, result, ready={}, artifact_dir=tmp_path)
    assert actual.layout == {"nodes": 1}
    assert actual.screenshot.status == ("failed" if failure else "available")
    executor._prepare_static_capture.assert_awaited_once()
    executor._capture_page.assert_awaited_once()
