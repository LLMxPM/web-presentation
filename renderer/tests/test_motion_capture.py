"""文件功能：验证 Renderer 按请求协议等待静态就绪，不依赖真实浏览器。"""
import pytest
from render_contracts.constants import RUNTIME_RENDER_PROTOCOL_VERSION_V2
from wp_renderer.engine.render_ready import wait_for_render_ready


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

