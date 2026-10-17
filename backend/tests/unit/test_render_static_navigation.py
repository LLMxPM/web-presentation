"""文件功能：验证页面渲染导航固定 capture 上下文，组件诊断不被误标为静态捕获。"""

from __future__ import annotations

import pytest

from app.services.rendering.coordinator import _ensure_render_identity_query, is_static_capture_operation
from app.services.rendering.snapshot_service import RenderSnapshotService
from render_contracts.constants import (
    OPERATION_COMPONENT_DIAGNOSE,
    OPERATION_PAGE_CAPTURE,
    OPERATION_PAGE_DIAGNOSE,
)

pytestmark = pytest.mark.unit


def test_static_capture_operation_only_covers_page_operations() -> None:
    assert is_static_capture_operation(OPERATION_PAGE_CAPTURE) is True
    assert is_static_capture_operation(OPERATION_PAGE_DIAGNOSE) is True
    assert is_static_capture_operation(OPERATION_COMPONENT_DIAGNOSE) is False


def test_existing_preview_url_gets_runtime_capture_and_identity_params() -> None:
    url = _ensure_render_identity_query(
        "http://runtime.local/__preview?keep=1",
        input_digest="digest-1",
        artifact_id="rt_1",
        static_capture=True,
    )

    assert "keep=1" in url
    assert "artifact=rt_1" in url
    assert "input_digest=digest-1" in url
    assert "runtimeCapture=1" in url
    assert _ensure_render_identity_query(url, input_digest="digest-1", artifact_id="rt_1", static_capture=True) == url


def test_component_diagnose_navigation_is_not_marked_as_capture() -> None:
    url = _ensure_render_identity_query(
        "http://runtime.local/__preview",
        input_digest="digest-1",
        artifact_id="rt_1",
        static_capture=False,
    )

    assert "runtimeCapture" not in url


def test_generated_preview_navigation_url_includes_capture_flag() -> None:
    url = RenderSnapshotService.build_preview_navigation_url(
        navigation_base_url="http://runtime.local",
        artifact_id="rt_1",
        preview_token="token-1",
        input_digest="digest-1",
        static_capture=True,
    )

    assert url.startswith("http://runtime.local/preview?")
    assert "runtimeCapture=1" in url
    assert "artifact=rt_1" in url
    assert "input_digest=digest-1" in url
