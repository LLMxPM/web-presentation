"""文件功能：验证页面与组件校验结果的模型侧精简、截断和写入结果压缩。"""

from __future__ import annotations

from app.ai.platform_tools import AgentToolResult
from app.ai.validation_result_formatter import (
    build_validation_text,
    build_validation_tool_result,
    compact_mutation_result,
)


def test_page_passed_without_issues_uses_short_success_summary() -> None:
    """无问题页面只保留通过结论，不展开正常布局项。"""

    text = build_validation_text(
        {
            "success": True,
            "status": "passed",
            "summary": "代码检查通过。",
            "diagnostics": [],
            "layout_analysis": {
                "text_layouts": [{"attention": "none", "line_count": 2}],
                "empty_regions": [],
            },
        },
        resource_type="page",
    )

    assert text == "检查通过，无警告"
    assert "line_count" not in text


def test_page_layout_warnings_are_aggregated_and_keep_location() -> None:
    """页面 warning 应合并布局类别计数，并保留 code、message 和定位。"""

    text = build_validation_text(
        {
            "success": True,
            "status": "passed",
            "summary": "代码检查通过。",
            "diagnostics": [{
                "severity": "warning",
                "code": "PAGE_RENDER_BOTTOM_OVERFLOW",
                "message": "页面底部超出画布 42px。",
                "location": {"selector": "footer", "line": 18},
            }],
            "layout_analysis": {
                "overflows": [{
                    "attention": "likely_issue",
                    "reason_codes": ["bottom_overflow"],
                    "message": "页面底部超出画布 42px。",
                    "target": {"label": "footer"},
                    "overflow_px": 42,
                }],
                "empty_regions": [{
                    "attention": "review",
                    "reason_codes": ["large_vertical_gap"],
                    "first": {"label": "content"},
                    "second": {"label": "footer"},
                    "height_px": 180,
                }],
            },
        },
        resource_type="page",
        detail=True,
    )

    assert "检查结论：passed_with_warnings" in text
    assert "布局：overflows=1、empty_regions=1" in text
    assert "[PAGE_RENDER_BOTTOM_OVERFLOW] 页面底部超出画布 42px。" in text
    assert "定位：footer" in text
    assert "[layout.empty_regions.large_vertical_gap] content与footer之间存在较大留白。" in text
    assert "facts=height_px=180" in text
    assert "layout_analysis" not in text
    assert "下一步：" in text


def test_validation_issues_are_capped_at_ten() -> None:
    """warning/error 合计最多返回十条，并报告隐藏数量。"""

    diagnostics = [
        {
            "severity": "warning",
            "code": f"W_{index}",
            "message": f"warning {index}",
        }
        for index in range(12)
    ]
    text = build_validation_text(
        {"success": True, "status": "passed", "diagnostics": diagnostics},
        resource_type="page",
    )

    assert sum(line.startswith("- [") for line in text.splitlines()) == 10
    assert "已省略 2 条 warning/error。" in text


def test_compile_error_keeps_code_location_and_detail_hint() -> None:
    """编译错误应保留稳定 code、文件行列和下一步提示。"""

    text = build_validation_text(
        {
            "success": False,
            "status": "failed",
            "summary": "编译失败。",
            "diagnostics": [{
                "severity": "error",
                "code": "COMPONENT_COMPILE_FAILED",
                "message": "模板解析失败。",
                "location": {"file": "src/Component.vue", "line": 12, "column": 4},
            }],
        },
        resource_type="component",
    )

    assert "检查结论：failed" in text
    assert "错误：" in text
    assert "[COMPONENT_COMPILE_FAILED] 模板解析失败。" in text
    assert "定位：src/Component.vue:12:4" in text
    assert "validate_entity" in text


def test_unavailable_is_short_and_does_not_look_like_candidate_error() -> None:
    """基础设施不可用只给出短结论和重试方向。"""

    text = build_validation_text(
        {
            "success": False,
            "status": "unavailable",
            "retryable": True,
            "diagnostics": [{
                "severity": "error",
                "code": "COMPONENT_CHECK_UNAVAILABLE",
                "message": "组件真实渲染诊断不可用。",
            }],
        },
        resource_type="component",
    )

    assert "检查结论：unavailable" in text
    assert "COMPONENT_CHECK_UNAVAILABLE" in text
    assert "detail=true" in text
    assert "retryable" not in text


def test_component_detail_controls_facts_but_not_scenario_profile() -> None:
    """组件默认只给问题上下文，detail=true 才增加受控 facts。"""

    result = {
        "success": True,
        "status": "passed_with_warnings",
        "summary": "组件可以编译并真实渲染；存在布局或资源警告。",
        "diagnostics": [{
            "severity": "warning",
            "code": "COMPONENT_RENDER_HORIZONTAL_OVERFLOW",
            "message": "preset:compact 水平溢出 8px。",
            "scenario_key": "preset:compact",
            "profile_key": "component-content-default.v1",
            "facts": {
                "overflow_px": 8,
                "frame": {"width": 320, "height": 180},
                "nodes": [{"selector": ".card"}, {"selector": ".title"}],
            },
        }],
        "scenarios": [
            {"key": "default", "status": "passed", "profile_key": "component-content-default.v1"},
            {"key": "preset:compact", "status": "passed_with_warnings", "profile_key": "component-content-default.v1"},
        ],
    }

    compact = build_validation_text(result, resource_type="component")
    detail = build_validation_text(result, resource_type="component", detail=True)

    assert "scenario=preset:compact" in compact
    assert "profile=component-content-default.v1" in compact
    assert "facts=" not in compact
    assert "facts=overflow_px=8, nodes_count=2" in detail
    assert "frame" not in detail
    assert "场景：已检查 2 个场景，通过 1 个，警告 1 个，失败 0 个；需关注：preset:compact。" in detail


def test_validate_tool_result_is_text_and_mutation_keeps_business_fields() -> None:
    """validate_entity 返回文本，写入结果删除完整校验字段但保留业务字段。"""

    validation = {
        "success": True,
        "status": "passed",
        "summary": "代码检查通过。",
        "diagnostics": [],
        "layout_analysis": {"overflows": []},
    }
    tool_result = build_validation_tool_result(validation, resource_type="page")
    assert isinstance(tool_result, AgentToolResult)
    assert tool_result.content == "检查通过，无警告"

    mutation = compact_mutation_result(
        {
            "success": True,
            "applied": True,
            "page_id": 31,
            "version_no": 4,
            "canonical_diff": "@@ ...",
            "diagnostics": [{"severity": "warning", "code": "W", "message": "有警告。"}],
            "layout_analysis": {"overflows": []},
            "code_check_summary": "代码检查通过。",
        },
        resource_type="page",
    )

    assert mutation["page_id"] == 31
    assert mutation["version_no"] == 4
    assert mutation["applied"] is True
    assert mutation["canonical_diff"] == "@@ ..."
    assert isinstance(mutation["validation"], str)
    assert "diagnostics" not in mutation
    assert "layout_analysis" not in mutation
    assert "code_check_summary" not in mutation


def test_component_failure_does_not_duplicate_top_level_and_nested_validation() -> None:
    """组件创建或元数据失败时只保留一份短文本 validation。"""

    validation = {
        "success": False,
        "valid": False,
        "status": "failed",
        "retryable": False,
        "summary": "组件渲染失败。",
        "validation_profile_version": "component-profiles.v1",
        "diagnostics": [{
            "severity": "error",
            "code": "COMPONENT_RENDER_EMPTY",
            "message": "default 没有可见的组件根内容。",
        }],
        "scenarios": [],
    }
    mutation = compact_mutation_result(
        {
            "success": False,
            "status": "failed",
            "summary": "组件渲染失败。",
            "message": "组件校验失败，未创建草稿。",
            "applied": False,
            "validation": validation,
            "diagnostics": validation["diagnostics"],
        },
        resource_type="component",
    )

    assert mutation["validation"].startswith("检查结论：failed")
    assert mutation["message"] == "组件校验失败，未创建草稿。"
    assert "diagnostics" not in mutation
    assert "status" not in mutation
    assert "summary" not in mutation
    assert isinstance(mutation["validation"], str)
