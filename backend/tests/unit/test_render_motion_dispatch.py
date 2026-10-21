"""文件功能：验证 Backend 按 Worker 能力选择渲染 v2 并拒绝向旧 Worker 派发时间轴选择器。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from render_contracts.constants import (
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_V2,
    RESULT_SCHEMA_VERSION,
)
from render_contracts.schema import WorkerCapabilities

from app.services.rendering.coordinator import RenderCoordinator

pytestmark = pytest.mark.unit


def _capabilities(*, v2: bool) -> WorkerCapabilities:
    """构造声明或不声明 v2 的 Worker 能力。"""

    return WorkerCapabilities.from_dict(
        {
            "worker_id": "worker-1",
            "worker_epoch": "epoch-1",
            "protocol_version": PROTOCOL_VERSION,
            "runtime_render_protocol_version": "render-ready.v1",
            "supported_protocol_versions": [PROTOCOL_VERSION, PROTOCOL_VERSION_V2] if v2 else [PROTOCOL_VERSION],
            "supported_runtime_protocol_versions": (
                ["render-ready.v1", "render-ready.v2"] if v2 else ["render-ready.v1"]
            ),
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "render_profile_digest": "prof",
            "environment_summary": {},
            "limits": {},
            "slot_state": "idle",
        }
    )


def _coordinator() -> RenderCoordinator:
    """构造仅用于请求装配的协调器，避免连接数据库或 HTTP。"""

    coordinator = RenderCoordinator.__new__(RenderCoordinator)
    coordinator.credentials = SimpleNamespace(  # type: ignore[attr-defined]
        load_secret=lambda: b"unit-test-secret",
        decrypt_sensitive_payload=lambda _value: {
            "preview_token": "tok",
            "preview_url": "http://runtime.example/preview?keep=1",
        },
    )
    coordinator.targets = SimpleNamespace(  # type: ignore[attr-defined]
        navigation_base_url=lambda: "http://runtime.example",
        asset_base_url=lambda: "http://assets.example",
        platform_asset_base_url=lambda: "http://platform-assets.example",
    )
    return coordinator


def _request(motion_snapshot: dict | None = None) -> SimpleNamespace:
    """构造持久化渲染请求的最小字段集合。"""

    operation_options: dict = {}
    if motion_snapshot is not None:
        operation_options["motion_snapshot"] = motion_snapshot
    return SimpleNamespace(
        id=1,
        operation="page.capture",
        request_digest="digest",
        workspace_id=1,
        trace_id="trace",
        snapshot_ref={
            "artifact_id": "artifact-1",
            "input_digest": "in-1",
            "preview_credentials": "cipher",
        },
        input_digest="in-1",
        render_profile_digest="prof",
        viewport={"width": 1280, "height": 720, "device_scale_factor": 1},
        operation_options=operation_options,
        deadline_at=datetime.now(UTC) + timedelta(seconds=60),
        schedule_category="background",
    )


def _attempt() -> SimpleNamespace:
    """构造已保留 attempt 的最小字段集合。"""

    return SimpleNamespace(
        worker_id="worker-1",
        worker_epoch="epoch-1",
        slot_generation=1,
        attempt_uid="attempt-1",
    )


def test_page_capture_with_selector_uses_v2_and_runtime_protocol() -> None:
    """带选择器的请求升为 v2，导航 URL 固定 runtimeCaptureProtocol=2。"""

    execution = _coordinator()._build_execution_request(
        request=_request({"timeline_id": "intro", "at_ms": 500}),
        attempt=_attempt(),
        capabilities=_capabilities(v2=True),
    )

    assert execution.contract_version == PROTOCOL_VERSION_V2
    assert execution.motion_snapshot is not None
    assert execution.motion_snapshot.to_dict() == {
        "timeline_id": "intro",
        "at_ms": 500,
        "visual_mode": "full",
    }
    assert "runtimeCaptureProtocol=2" in execution.preview_access.navigation_base_url
    assert execution.preview_access.runtime_protocol_version == "render-ready.v2"


def test_page_capture_without_selector_uses_v2_for_default_poster() -> None:
    """支持 v2 的 Worker 默认截图走 poster 采样，不再落回 v1 静态首帧。"""

    execution = _coordinator()._build_execution_request(
        request=_request(),
        attempt=_attempt(),
        capabilities=_capabilities(v2=True),
    )

    assert execution.contract_version == PROTOCOL_VERSION_V2
    assert execution.motion_snapshot is None
    assert "runtimeCaptureProtocol=2" in execution.preview_access.navigation_base_url


def test_worker_with_control_v2_but_runtime_v1_is_rejected() -> None:
    """只声明控制协议 v2、未声明 render-ready.v2 的 Worker 不能承接捕获。"""

    capabilities = replace(_capabilities(v2=True), supported_runtime_protocol_versions=("render-ready.v1",))
    with pytest.raises(Exception, match="render-ready.v2"):
        _coordinator()._build_execution_request(
            request=_request(),
            attempt=_attempt(),
            capabilities=capabilities,
        )


def test_selector_to_v1_worker_fails_before_http() -> None:
    """旧 Worker 不能收到 v2 选择器，派发前明确失败。"""

    with pytest.raises(Exception, match="internal/render/v2"):
        _coordinator()._build_execution_request(
            request=_request({"timeline_id": "intro", "at_label": "detail"}),
            attempt=_attempt(),
            capabilities=_capabilities(v2=False),
        )


def test_legacy_page_capture_without_selector_stays_v1_on_old_worker() -> None:
    """无选择器的旧 Worker 请求保持 v1，不因能力探测改写契约。"""

    execution = _coordinator()._build_execution_request(
        request=_request(),
        attempt=_attempt(),
        capabilities=_capabilities(v2=False),
    )
    assert execution.contract_version == PROTOCOL_VERSION
    assert execution.motion_snapshot is None
    assert execution.preview_access.runtime_protocol_version == "render-ready.v1"
    assert "runtimeCaptureProtocol" not in execution.preview_access.navigation_base_url


def test_selector_is_rejected_for_non_page_operation() -> None:
    """组件诊断没有页面时间轴，选择器在派发前明确拒绝。"""

    request = _request({"timeline_id": "intro"})
    request.operation = "component.diagnose"
    with pytest.raises(Exception, match="只支持页面"):
        _coordinator()._build_execution_request(
            request=request,
            attempt=_attempt(),
            capabilities=_capabilities(v2=True),
        )
