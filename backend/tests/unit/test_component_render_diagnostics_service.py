"""文件功能：验证组件真实渲染诊断的场景归一化、布局语义、失败分类和稳定校验 profile。"""

from __future__ import annotations

from app.models.enums import WorkspaceComponentType
from app.services.component_render_diagnostics_service import (
    ComponentCandidateRenderError,
    ComponentRenderDiagnosticsService,
)
from app.services.component_render_result import build_component_layout_diagnostics
from app.services.component_render_scenarios import build_component_render_scenarios
from app.services.component_validation_profile import build_component_validation_profile
from app.services.capture_viewport_resolver import CaptureViewport


class RaisingPlaywrightQueue:
    """始终抛出指定异常的浏览器队列替身。"""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def run_with_browser(self, *args: object, **kwargs: object) -> object:
        """模拟池内诊断失败。"""

        raise self.error


def test_component_scenarios_should_merge_defaults_and_limit_presets() -> None:
    """preset 应覆盖默认状态，并限制一次检查的浏览器场景数。"""

    ready_payload = {
        "defaultState": {
            "props": {"title": "默认", "width": 960},
            "slots": {"default": []},
            "mocks": {"loading": False},
            "activePresetKey": None,
        },
        "schema": {
            "presets": [
                {"key": f"case-{index}", "props": {"title": f"场景 {index}"}}
                for index in range(12)
            ],
        },
    }

    scenarios, truncated = build_component_render_scenarios(ready_payload)

    assert len(scenarios) == 11
    assert truncated == 2
    assert scenarios[1].key == "preset:case-0"
    assert scenarios[1].state["props"] == {"title": "场景 0", "width": 960}
    assert scenarios[1].state["activePresetKey"] == "case-0"


def test_component_layout_should_distinguish_empty_error_and_overflow_warnings() -> None:
    """空白结果应阻断，溢出与裁切应提供带事实的 warning。"""

    empty = build_component_layout_diagnostics(
        {"available": True, "visible_root_count": 0, "root": None},
        "default",
        "component-content-default.v1",
    )
    warnings = build_component_layout_diagnostics(
        {
            "available": True,
            "visible_root_count": 1,
            "root": {"width": 1000, "height": 560},
            "frame": {"width": 960, "height": 540},
            "intersection_area": 518400,
            "overflow": {"horizontal_px": 40, "vertical_px": 20},
            "clipped": [{"selector_hint": ".card", "clipped_x_px": 10, "clipped_y_px": 0}],
        },
        "preset:compact",
        "component-content-default.v1",
    )

    assert empty[0]["severity"] == "error"
    assert empty[0]["code"] == "COMPONENT_RENDER_EMPTY"
    assert {item["code"] for item in warnings} == {
        "COMPONENT_RENDER_HORIZONTAL_OVERFLOW",
        "COMPONENT_RENDER_VERTICAL_OVERFLOW",
        "COMPONENT_RENDER_CLIPPED",
    }
    assert all(item["scenario_key"] == "preset:compact" for item in warnings)


def test_component_validation_profiles_should_be_type_specific_and_project_independent() -> None:
    """三类组件应使用固定 profile，页面尺寸与字号仅作为临时 artifact 配置。"""

    page_key, page_options = build_component_validation_profile(WorkspaceComponentType.PAGE_COMPONENT)
    content_key, content_options = build_component_validation_profile(WorkspaceComponentType.CONTENT_COMPONENT)
    atomic_key, atomic_options = build_component_validation_profile(WorkspaceComponentType.ATOMIC_COMPONENT)

    assert page_key == "component-page-landscape.v1"
    assert page_options.placement.padding == 0
    assert page_options.placement.height_mode == "percent"
    assert content_key == "component-content-default.v1"
    assert content_options.placement.width_value == 960
    assert content_options.page.base_font_size == "20px"
    assert atomic_key == "component-atomic-default.v1"
    assert atomic_options.placement.width_value == 640


async def test_component_candidate_error_should_not_be_reported_as_infrastructure_unavailable() -> None:
    """组件自身启动错误应返回 failed，不能误导模型原样重试。"""

    service = ComponentRenderDiagnosticsService(
        RaisingPlaywrightQueue(ComponentCandidateRenderError("setup 执行失败")),  # type: ignore[arg-type]
    )

    result = await service.diagnose_preview(
        "http://runtime.test/preview",
        CaptureViewport(width=1920, height=1080),
        profile_key="component-content-default.v1",
    )

    assert result["status"] == "failed"
    assert result["retryable"] is False
    assert result["diagnostics"][0]["code"] == "COMPONENT_PREVIEW_BOOTSTRAP_FAILED"


async def test_component_infrastructure_error_should_be_retryable() -> None:
    """浏览器池异常应返回 unavailable，提示模型不要无依据修改候选。"""

    service = ComponentRenderDiagnosticsService(
        RaisingPlaywrightQueue(RuntimeError("browser pool unavailable")),  # type: ignore[arg-type]
    )

    result = await service.diagnose_preview(
        "http://runtime.test/preview",
        CaptureViewport(width=1920, height=1080),
        profile_key="component-content-default.v1",
    )

    assert result["status"] == "unavailable"
    assert result["retryable"] is True
    assert result["diagnostics"][0]["code"] == "COMPONENT_CHECK_UNAVAILABLE"
