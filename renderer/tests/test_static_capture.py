"""文件功能：验证 Renderer 捕获静态上下文、目标路由与视频首帧结果映射（不依赖真实浏览器）。"""

from __future__ import annotations

import pytest

from wp_renderer.engine.render_ready import normalize_runtime_route, validate_static_render_bridge
from wp_renderer.engine.static_media import (
    MIN_STATIC_MEDIA_TIMEOUT_MS,
    prepare_static_capture,
    static_capture_error,
)

pytestmark = pytest.mark.unit


def _bridge(**overrides: object) -> dict[str, object]:
    """构造捕获页面通过校验的 render-ready 桥状态。"""

    base: dict[str, object] = {
        "protocol": "render-ready.v1",
        "executionContext": "capture",
        "entryPath": "/cover",
        "routePath": "/cover",
    }
    base.update(overrides)
    return base


def test_static_bridge_accepts_capture_context_and_matching_route() -> None:
    assert validate_static_render_bridge(_bridge()) is None
    assert validate_static_render_bridge(_bridge(entryPath="/cover?x=1", routePath="/cover/")) is None
    assert validate_static_render_bridge(_bridge(entryPath="", routePath="/cover")) is None


@pytest.mark.parametrize(
    ("bridge", "message"),
    [
        (None, "缺少可核对"),
        (_bridge(executionContext="presentation"), "未进入捕获执行上下文"),
        (_bridge(executionContext=""), "未进入捕获执行上下文"),
        (_bridge(routePath=""), "缺少 routePath"),
        (_bridge(entryPath="/intro"), "捕获目标路由不一致"),
    ],
)
def test_static_bridge_rejects_missing_or_mismatched_static_state(
    bridge: dict[str, object] | None,
    message: str,
) -> None:
    error = validate_static_render_bridge(bridge)
    assert error is not None
    assert message in error


def test_normalize_runtime_route_ignores_query_hash_and_trailing_slash() -> None:
    assert normalize_runtime_route("/cover/?mode=normal") == "/cover"
    assert normalize_runtime_route("cover") == "/cover"
    assert normalize_runtime_route("/") == "/"
    assert normalize_runtime_route("") == ""


def test_static_capture_error_returns_layer_and_media_issues() -> None:
    assert static_capture_error({"ok": True}) is None
    error = static_capture_error({
        "ok": False,
        "layerIssue": "捕获画布应只保留一个页面层，实际 2 个",
        "issues": ["视频首帧在限定时间内不可用：/video/demo.webm"],
    })
    assert error is not None
    assert "页面层" in error
    assert "视频首帧" in error
    assert static_capture_error({}) == "静态捕获探针返回无效结果。"


@pytest.mark.asyncio
async def test_prepare_static_capture_passes_expected_route_and_bounded_timeout() -> None:
    calls: list[dict[str, object]] = []

    class FakePage:
        async def evaluate(self, script: str, payload: dict[str, object]) -> dict[str, object]:
            calls.append({"script": script, "payload": payload})
            return {"ok": True, "totalMedia": 0}

    result = await prepare_static_capture(FakePage(), expected_route="/cover", timeout_ms=1)

    assert result["ok"] is True
    assert calls[0]["payload"] == {"timeoutMs": MIN_STATIC_MEDIA_TIMEOUT_MS, "expectedRoute": "/cover"}
    assert "videos" in calls[0]["script"]
