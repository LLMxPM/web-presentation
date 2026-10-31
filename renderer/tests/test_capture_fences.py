"""文件功能：以可控 PNG 与关闭事件验证取消、图片期限和迟到结果的发布围栏，不启动浏览器。"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from render_contracts.errors import RenderExecutionError
from wp_renderer.engine.executor import RenderExecutor
from wp_renderer.engine.static_presentation import require_static_presentation


CASES = json.loads((Path(__file__).parents[2] / "tests/fixtures/static-capture-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", [case for case in CASES if "receipt" in case], ids=lambda case: case["name"])
def test_runtime_receipt_maps_to_frozen_capture_semantics(case):
    """Runtime 的共享回执必须在 Renderer 产生相同内容/资源错误分类。"""
    if case["error"]:
        with pytest.raises(RenderExecutionError) as caught:
            require_static_presentation({"staticPresentation": case["receipt"]})
        assert caught.value.error.code == case["error"]
        assert caught.value.error.retryable == case["phase"]["retryable"]
    else:
        require_static_presentation({"staticPresentation": case["receipt"]})


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["cancel", "deadline", "shutdown", "image_phase"])
async def test_late_png_is_not_written_or_registered(boundary, tmp_path):
    """截图 Promise 返回时必须重新检查归属和期限，不能注册迟到 PNG。"""
    execution = SimpleNamespace(cancel_requested=False, artifacts={})
    executor = RenderExecutor(settings=SimpleNamespace(max_png_bytes=1024), slot=None, execution=execution)

    async def screenshot(**kwargs):
        """模拟截图在退出边界后才返回字节，不需要真实 Chromium。"""
        if boundary == "cancel":
            execution.cancel_requested = True
        if boundary == "shutdown":
            executor._shutdown_started = True
        return b"png"

    executor._page = SimpleNamespace(screenshot=screenshot)
    if boundary == "deadline":
        from wp_renderer.engine.executor import DeadlineClock
        executor._deadline = DeadlineClock(deadline_monotonic=0)
    with pytest.raises(RenderExecutionError):
        await executor._capture_page(tmp_path, is_current=lambda: boundary != "image_phase")
    assert execution.artifacts == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["capture", "cleaning"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_slot_publishes_only_after_cleanup_and_discards_cancelled_result(when, cancel, tmp_path, monkeypatch):
    """执行器返回成功或清理时收到取消都必须无结果、无临时文件且释放槽位。"""
    from test_slot_controller import _make_request
    from wp_renderer.control.slot import SlotController
    from wp_renderer.config import RendererSettings

    entered, release = asyncio.Event(), asyncio.Event()

    class Executor:
        """可控执行器让取消精确命中返回/清理窗口，并故意迟到返回成功。"""
        def __init__(self, *, execution, settings, slot):
            self.execution = execution
            self.base = RenderExecutor(execution=execution, settings=settings, slot=slot)

        async def execute(self, *, artifact_dir):
            path = artifact_dir / "page.png"
            path.write_bytes(b"png")
            self.execution.artifacts["page.png"] = path
            if when == "capture":
                entered.set()
                await release.wait()
            return self.base._base_result()

        async def shutdown(self):
            if when == "cleaning":
                entered.set()
            await release.wait()

    monkeypatch.setattr("wp_renderer.engine.executor.RenderExecutor", Executor)
    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    slot.settings = RendererSettings(render_service_credential="renderer-test-secret", render_service_credential_file=None,
        render_workspace_dir=str(tmp_path), render_worker_id="renderer-local", render_worker_epoch="epoch-1")
    try:
        status, _ = await slot.accept(_make_request(attempt_id=f"late-{when}"))
        assert status == 202
        await asyncio.wait_for(entered.wait(), timeout=2)
        if when == "cleaning":
            # PNG 虽已返回，清理尚未完成时也不能提前披露成功或产物。
            receipt = slot.build_receipt(slot.get_execution(f"late-{when}"))
            assert receipt.status == "cleaning"
            assert receipt.result_descriptor is None
            assert slot.artifact_path(f"late-{when}", "page.png") is None
        if cancel:
            slot.request_cancel(f"late-{when}")
        task = slot._task
        release.set()
        done, _ = await asyncio.wait({task}, timeout=2)
        assert task in done
        task.result()
        execution = slot.get_execution(f"late-{when}")
        receipt = slot.build_receipt(execution)
        assert receipt.status == ("cancelled" if cancel else "succeeded")
        if cancel:
            assert receipt.result_descriptor is None
            assert receipt.resource_state == "released"
        else:
            assert receipt.result_descriptor is not None
            assert receipt.resource_state == "retained"
            assert slot.artifact_path(f"late-{when}", "page.png") is not None
            assert slot.mark_consumed(f"late-{when}")
        assert not slot.busy
        assert list(tmp_path.iterdir()) == []
    finally:
        release.set()
        await slot.shutdown(grace_seconds=1)


@pytest.mark.asyncio
async def test_partial_browser_launch_is_always_closed(monkeypatch, tmp_path):
    """启动阶段异常也必须进入 finally，不能只关闭已导航的浏览器。"""
    from test_slot_controller import _make_request
    executor = RenderExecutor(settings=SimpleNamespace(), slot=SimpleNamespace(settings=SimpleNamespace(render_profile_digest="")),
        execution=SimpleNamespace(request=_make_request(), cancel_requested=False))
    executor._launch_browser = AsyncMock(side_effect=RuntimeError("context failed"))
    executor.shutdown = AsyncMock()
    with pytest.raises(RuntimeError, match="context failed"):
        await executor.execute(artifact_dir=tmp_path)
    executor.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_component_diagnose_rejects_interactive_execution_context():
    """组件诊断也必须走静态上下文，不能以 Editor 允许手势的策略执行远程渲染。"""
    executor = RenderExecutor(settings=None, slot=None, execution=None)
    request = SimpleNamespace(operation="component.diagnose")
    await executor._prepare_static_capture(request, {"bridge": {"executionContext": "capture"}})
    with pytest.raises(RenderExecutionError) as caught:
        await executor._prepare_static_capture(request, {"bridge": {"executionContext": "interactive-preview"}})
    assert caught.value.error.code == "RENDER_CONTRACT_MISMATCH"


@pytest.mark.asyncio
async def test_timed_out_image_phase_preserves_layout_and_discards_late_png(tmp_path):
    """图片阶段预算先耗尽时，布局成功保持；迟到的真实捕获函数不得写磁盘。"""
    from render_contracts.schema import ExecutionResult
    from wp_renderer.engine.joint_capture import append_screenshot
    from test_slot_controller import _make_request
    from dataclasses import replace

    entered, release = asyncio.Event(), asyncio.Event()
    request = replace(_make_request(), operation_options={"capture_screenshot": True})
    execution = SimpleNamespace(request=request, cancel_requested=False, artifacts={})
    executor = RenderExecutor(settings=SimpleNamespace(max_png_bytes=1024), slot=None, execution=execution)
    executor._deadline = SimpleNamespace(remaining_seconds=lambda: 5)
    executor._prepare_static_capture = AsyncMock()

    async def screenshot(**kwargs):
        """PNG 底层任务保持未取消，直到测试显式放行。"""
        entered.set()
        await release.wait()
        return b"png"

    executor._page = SimpleNamespace(screenshot=screenshot)
    tasks = []

    async def timeout(awaitable, **kwargs):
        """只放弃当前阶段的等待，符合禁止取消 Playwright Task 的约束。"""
        tasks.append(asyncio.create_task(awaitable))
        await entered.wait()
        raise TimeoutError

    executor._await_without_cancelling = timeout
    result = ExecutionResult("r", "a", "w", "e", 1, "page.diagnose", "i", "p", "d", "render-result.v1", {}, layout={"nodes": 1})
    actual = await append_screenshot(executor, result, ready={}, artifact_dir=tmp_path)
    assert actual.layout == {"nodes": 1}
    assert actual.screenshot.reason_code == "SCREENSHOT_DEADLINE_EXCEEDED"
    assert not tasks[0].cancelled()
    executor._deadline.check = lambda **kwargs: None
    release.set()
    with pytest.raises(RenderExecutionError):
        await tasks[0]
    assert execution.artifacts == {}
    assert list(tmp_path.iterdir()) == []
