"""文件功能：把组件浏览器几何事实转换为模型可消费的稳定布局诊断结果。"""

from __future__ import annotations

COMPONENT_RENDER_SOURCE = "component-render"
COMPONENT_LAYOUT_SOURCE = "component-layout"


def build_component_diagnostic(
    *,
    severity: str,
    source: str,
    code: str,
    message: str,
    profile_key: str,
    scenario_key: str | None = None,
    facts: dict[str, object] | None = None,
    suggestion: str | None = None,
) -> dict[str, object]:
    """构造模型可消费的稳定组件诊断项。"""

    return {
        "severity": severity,
        "stage": "render",
        "source": source,
        "code": code,
        "message": message,
        "scenario_key": scenario_key,
        "profile_key": profile_key,
        "location": None,
        "facts": facts or {},
        "suggestion": suggestion,
    }


def has_component_errors(diagnostics: list[dict[str, object]]) -> bool:
    """判断诊断列表是否包含阻断错误。"""

    return any(item.get("severity") == "error" for item in diagnostics)


def build_component_layout_diagnostics(
    layout: object,
    scenario_key: str,
    profile_key: str,
) -> list[dict[str, object]]:
    """把浏览器几何事实转换为稳定组件布局诊断。"""

    if not isinstance(layout, dict) or not layout.get("available"):
        return [build_component_diagnostic(
            severity="error",
            source=COMPONENT_LAYOUT_SOURCE,
            code="COMPONENT_RENDER_EMPTY",
            message=str(layout.get("reason") if isinstance(layout, dict) else "组件预览没有可测量结果。"),
            scenario_key=scenario_key,
            profile_key=profile_key,
        )]
    facts = dict(layout)
    diagnostics: list[dict[str, object]] = []
    if int(layout.get("visible_root_count") or 0) <= 0 or not isinstance(layout.get("root"), dict):
        diagnostics.append(build_component_diagnostic(
            severity="error",
            source=COMPONENT_LAYOUT_SOURCE,
            code="COMPONENT_RENDER_EMPTY",
            message=f"{scenario_key} 没有可见的组件根内容。",
            scenario_key=scenario_key,
            profile_key=profile_key,
            facts=facts,
            suggestion="检查根节点的条件渲染、display、visibility、opacity 和宽高。",
        ))
        return diagnostics
    if float(layout.get("intersection_area") or 0) <= 0:
        diagnostics.append(build_component_diagnostic(
            severity="error",
            source=COMPONENT_LAYOUT_SOURCE,
            code="COMPONENT_RENDER_OUTSIDE_FRAME",
            message=f"{scenario_key} 的可见内容完全位于 placement frame 外。",
            scenario_key=scenario_key,
            profile_key=profile_key,
            facts=facts,
            suggestion="检查绝对定位、transform 和固定尺寸，确保组件相对宿主 frame 布局。",
        ))
    overflow = layout.get("overflow") if isinstance(layout.get("overflow"), dict) else {}
    for direction, code in (
        ("horizontal_px", "COMPONENT_RENDER_HORIZONTAL_OVERFLOW"),
        ("vertical_px", "COMPONENT_RENDER_VERTICAL_OVERFLOW"),
    ):
        pixels = float(overflow.get(direction) or 0)
        if pixels > 2:
            diagnostics.append(build_component_diagnostic(
                severity="warning",
                source=COMPONENT_LAYOUT_SOURCE,
                code=code,
                message=f"{scenario_key} 在 placement frame 中{('水平' if direction == 'horizontal_px' else '垂直')}溢出 {pixels:.0f}px。",
                scenario_key=scenario_key,
                profile_key=profile_key,
                facts={"overflow_px": pixels, "frame": layout.get("frame"), "root": layout.get("root")},
                suggestion="检查固定宽高、padding、box-sizing 和响应式尺寸约束。",
            ))
    clipped = layout.get("clipped")
    if isinstance(clipped, list) and clipped:
        diagnostics.append(build_component_diagnostic(
            severity="warning",
            source=COMPONENT_LAYOUT_SOURCE,
            code="COMPONENT_RENDER_CLIPPED",
            message=f"{scenario_key} 中发现 {len(clipped)} 个可能被 overflow 裁切的节点。",
            scenario_key=scenario_key,
            profile_key=profile_key,
            facts={"nodes": clipped},
            suggestion="确认裁切是否为设计意图；若不是，调整容器尺寸或 overflow 规则。",
        ))
    return diagnostics
