"""文件功能：验证 Renderer v2 时间轴选择器派发、回执核对与旧 Worker 兼容协议。"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from render_contracts.constants import (
    PROTOCOL_VERSION_V2,
    RUNTIME_RENDER_PROTOCOL_VERSION_V2,
)
from render_contracts.motion import MotionSnapshot

from wp_renderer.engine.executor import DeadlineClock, RenderExecutor
from wp_renderer.engine.render_ready import wait_for_render_ready

pytestmark = pytest.mark.unit


def _executor(page: object, *, contract_version: str = PROTOCOL_VERSION_V2) -> RenderExecutor:
    """构造只用于单方法验证的执行器，避免启动浏览器。"""

    request = SimpleNamespace(
        motion_snapshot=MotionSnapshot(timeline_id="intro", at_ms=500, visual_mode="reduced"),
        contract_version=contract_version,
    )
    executor = RenderExecutor(
        settings=SimpleNamespace(),
        slot=SimpleNamespace(),
        execution=SimpleNamespace(request=request),
    )
    executor._deadline = DeadlineClock(deadline_monotonic=time.monotonic() + 10)  # type: ignore[attr-defined]
    executor._page = page  # type: ignore[attr-defined]
    return executor


@pytest.mark.asyncio
async def test_apply_motion_snapshot_checks_receipt_and_records_state() -> None:
    """选择器按 camelCase 传入 Runtime，成功回执写入结果状态。"""

    calls: list[dict[str, object]] = []

    class FakePage:
        async def evaluate(self, script: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(payload)
            assert "__RUNTIME_APPLY_MOTION_SNAPSHOT__" in script
            return {
                "available": True,
                "receipt": {
                    "status": "applied",
                    "timeline_id": "intro",
                    "plan_digest": "plan-1",
                    "sampled_time_ms": 500,
                    "state_digest": "state-1",
                    "visual_mode": "reduced",
                },
            }

    executor = _executor(FakePage())
    await executor._apply_motion_snapshot(executor.execution.request)  # type: ignore[attr-defined]

    assert calls == [{"timelineId": "intro", "atMs": 500, "visualMode": "reduced"}]
    assert executor._applied_motion is not None  # type: ignore[attr-defined]
    assert executor._applied_motion.to_dict() == {  # type: ignore[attr-defined]
        "status": "applied",
        "timeline_id": "intro",
        "plan_digest": "plan-1",
        "sampled_time_ms": 500,
        "state_digest": "state-1",
        "visual_mode": "reduced",
    }


@pytest.mark.asyncio
async def test_apply_motion_snapshot_rejects_missing_bridge_or_mismatched_receipt() -> None:
    """显式选择器在旧 Runtime 或缺字段时明确失败，不静默截取其他时刻。"""

    class NoBridgePage:
        async def evaluate(self, script: str, payload: dict[str, object]) -> dict[str, object]:
            return {"available": False}

    executor = _executor(NoBridgePage())
    with pytest.raises(Exception, match="未提供时间轴采样能力"):
        await executor._apply_motion_snapshot(executor.execution.request)  # type: ignore[attr-defined]

    class MismatchPage:
        async def evaluate(self, script: str, payload: dict[str, object]) -> dict[str, object]:
            return {
                "available": True,
                "receipt": {
                    "status": "applied",
                    "timeline_id": "other",
                    "plan_digest": "plan-1",
                    "sampled_time_ms": 500,
                    "state_digest": "state-1",
                    "visual_mode": "reduced",
                },
            }

    executor = _executor(MismatchPage())
    with pytest.raises(Exception, match="不一致"):
        await executor._apply_motion_snapshot(executor.execution.request)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_wait_for_render_ready_uses_requested_protocol_version() -> None:
    """v2 请求等待 render-ready.v2，而不是隐式复用 v1。"""

    calls: list[dict[str, object]] = []

    class FakePage:
        async def evaluate(self, script: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append(payload)
            return {"ok": True, "bridge": {}}

    await wait_for_render_ready(
        FakePage(),
        timeout_ms=1000,
        protocol=RUNTIME_RENDER_PROTOCOL_VERSION_V2,
    )
    assert calls[0]["protocol"] == RUNTIME_RENDER_PROTOCOL_VERSION_V2

