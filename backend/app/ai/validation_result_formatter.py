"""文件功能：把页面与组件完整校验结果压缩为模型侧可读的短文本和轻量写入结果。"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.ai.platform_tools import AgentToolResult, RECOVERABLE_TOOL_ERROR_KIND


MAX_VALIDATION_ISSUES = 10
_PAGE_LAYOUT_SECTIONS = (
    "text_layouts",
    "item_groups",
    "overflows",
    "spatial_relations",
    "empty_regions",
)
_LAYOUT_REASON_MESSAGES = {
    "bottom_overflow": "页面底部超出画布。",
    "text_clipped": "内容可能被容器裁切。",
    "single_item_last_row": "最后一行只包含一个项目。",
    "independent_surfaces_touching": "独立视觉表面之间存在贴合。",
    "large_vertical_gap": "内容区与后续区域之间存在较大留白。",
    "leading_gap": "内容顶部存在较大留白。",
    "right_gap": "内容右侧存在较大留白。",
    "interior_gap": "内容之间存在较大内部留白。",
}
_RESOURCE_LABELS = {"page": "页面", "component": "组件"}
_MUTATION_VALIDATION_FIELDS = {
    "diagnostics",
    "layout_analysis",
    "code_check_summary",
    "artifact_id",
    "schema_version",
    "source",
    "status",
    "valid",
    "stages",
    "scenarios",
    "validation_profile_version",
    "profile_key",
}
_FACT_KEYS = (
    "line_count",
    "break_kind",
    "stability",
    "item_count",
    "row_count",
    "last_row_count",
    "wrap_margin_px",
    "overflow_px",
    "overflow_right_px",
    "overflow_left_px",
    "overflow_top_px",
    "overflow_bottom_px",
    "visible_ratio",
    "clipping",
    "distance_px",
    "height_px",
    "width_px",
    "ratio_of_canvas",
    "ratio_of_parent",
    "geometry_reliability",
    "skipped_count",
    "limit",
    "gap_top_px",
    "gap_bottom_px",
    "gap_left_px",
    "gap_right_px",
    "canvas_height_px",
    "canvas_width_px",
    "intersection_area",
    "visible_root_count",
    "frame_width_px",
    "frame_height_px",
    "root_width_px",
    "root_height_px",
    "selector_hint",
)


def build_validation_text(
    result: Mapping[str, Any],
    *,
    resource_type: str,
    detail: bool = False,
    include_next_step: bool = True,
) -> str:
    """把完整校验结果渲染为有界短文本，保留模型修复所需的错误上下文。"""

    issues = _collect_issues(result, resource_type=resource_type, detail=detail)
    visible_issues = issues[:MAX_VALIDATION_ISSUES]
    hidden_count = max(0, len(issues) - len(visible_issues))
    status = _resolve_status(result)
    has_errors = any(item["severity"] == "error" for item in issues)
    has_warnings = any(item["severity"] != "error" for item in issues)
    if status != "unavailable":
        if has_errors:
            status = "failed"
        elif status == "passed" and has_warnings:
            status = "passed_with_warnings"
    if status == "passed" and not issues:
        return "检查通过，无警告"
    summary = _resolve_summary(
        result,
        resource_type=resource_type,
        status=status,
        warning_count=sum(item["severity"] != "error" for item in issues),
    )
    scenario_summary = _build_scenario_summary(result)
    layout_summary = _build_layout_summary(result, resource_type=resource_type)

    lines = [f"检查结论：{status}", f"摘要：{summary}"]
    if scenario_summary:
        lines.append(f"场景：{scenario_summary}")
    if layout_summary:
        lines.append(f"布局：{layout_summary}")

    errors = [item for item in visible_issues if item["severity"] == "error"]
    warnings = [item for item in visible_issues if item["severity"] != "error"]
    if errors:
        lines.append("错误：")
        lines.extend(_format_issue(item, detail=detail) for item in errors)
    if warnings:
        lines.append("警告：")
        lines.extend(_format_issue(item, detail=detail) for item in warnings)
    if hidden_count:
        lines.append(f"已省略 {hidden_count} 条 warning/error。")

    if include_next_step and (errors or warnings or status == "unavailable"):
        lines.append("下一步：如需查看诊断明细，请使用同一目标和候选 mode 调用 validate_entity；需要更完整信息时设置 detail=true。")
    return "\n".join(lines)


def build_validation_tool_result(
    result: Mapping[str, Any],
    *,
    resource_type: str,
    detail: bool = False,
) -> AgentToolResult:
    """构造 validate_entity 使用的纯文本工具结果。"""

    return AgentToolResult(
        content=build_validation_text(
            result,
            resource_type=resource_type,
            detail=detail,
            include_next_step=not detail,
        )
    )


def compact_mutation_result(result: Any, *, resource_type: str) -> Any:
    """移除写入工具中的完整校验对象，保留业务字段和短文本校验结论。"""

    if resource_type not in {"page", "component"} or not isinstance(result, dict):
        return result

    if result.get("kind") == RECOVERABLE_TOOL_ERROR_KIND:
        data = result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("validation"), dict):
            return result
        return _compact_recoverable_error(deepcopy(result), resource_type=resource_type)

    validation = result.get("validation")
    is_full_validation_result = _looks_like_validation_result(result)
    if not isinstance(validation, dict) and not is_full_validation_result:
        return result

    compacted = deepcopy(result)
    if isinstance(validation, dict):
        compacted["validation"] = build_validation_text(
            validation,
            resource_type=resource_type,
        )
    elif is_full_validation_result:
        compacted["validation"] = build_validation_text(
            compacted,
            resource_type=resource_type,
        )

    for field_name in _MUTATION_VALIDATION_FIELDS:
        compacted.pop(field_name, None)
    if is_full_validation_result and isinstance(result.get("status"), str):
        compacted.pop("summary", None)
    return compacted


def _compact_recoverable_error(result: dict[str, Any], *, resource_type: str) -> dict[str, Any]:
    """压缩组件异步任务使用的 recoverable validation 错误。"""

    data = result.get("data")
    if not isinstance(data, dict):
        return result
    validation = data.get("validation")
    if not isinstance(validation, dict):
        return result

    data["validation"] = build_validation_text(
        validation,
        resource_type=resource_type,
    )
    result["data"] = data
    error = result.get("error")
    if isinstance(error, dict):
        error["hint"] = "根据校验提示修正候选；如需诊断明细，请调用 validate_entity 并设置 detail=true。"
    return result


def _looks_like_validation_result(result: Mapping[str, Any]) -> bool:
    """判断一个写入结果是否是未包装的完整代码校验结果。"""

    return any(
        field_name in result
        for field_name in ("diagnostics", "layout_analysis", "validation_profile_version", "stages")
    )


def _collect_issues(
    result: Mapping[str, Any],
    *,
    resource_type: str,
    detail: bool,
) -> list[dict[str, Any]]:
    """收集 Runtime 诊断和页面布局分析中的 actionable 问题。"""

    issues: list[dict[str, Any]] = []
    diagnostics = result.get("diagnostics")
    if isinstance(diagnostics, list):
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                continue
            severity = str(diagnostic.get("severity") or "warning")
            if severity == "info":
                continue
            code = str(diagnostic.get("code") or "").strip()
            message = str(diagnostic.get("message") or "").strip()
            if not code or not message:
                continue
            issues.append({
                "severity": "error" if severity == "error" else "warning",
                "code": code,
                "message": message,
                "target": diagnostic.get("location"),
                "scenario": diagnostic.get("scenario_key"),
                "profile": diagnostic.get("profile_key"),
                "facts": _compact_facts(diagnostic.get("facts")),
            })

    if resource_type == "page":
        _append_page_layout_issues(issues, result.get("layout_analysis"), detail=detail)
    deduplicated = _deduplicate_issues(issues)
    return sorted(deduplicated, key=lambda item: 0 if item["severity"] == "error" else 1)


def _append_page_layout_issues(
    issues: list[dict[str, Any]],
    layout_analysis: Any,
    *,
    detail: bool,
) -> None:
    """把页面布局分析中带关注级别的条目转换为 warning。"""

    if not isinstance(layout_analysis, dict):
        return
    for section in _PAGE_LAYOUT_SECTIONS:
        entries = layout_analysis.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("attention") not in {"review", "likely_issue"}:
                continue
            reason_codes = entry.get("reason_codes")
            first_reason = (
                str(reason_codes[0])
                if isinstance(reason_codes, list) and reason_codes and reason_codes[0]
                else "attention_required"
            )
            issues.append({
                "severity": "warning",
                "code": f"layout.{section}.{first_reason}",
                "message": _layout_message(entry, section),
                "target": _layout_target(entry),
                "scenario": None,
                "profile": None,
                "facts": _layout_facts(entry) if detail else None,
            })


def _layout_message(entry: Mapping[str, Any], section: str) -> str:
    """读取布局条目已有提示，缺失时生成简短可读描述。"""

    message = str(entry.get("message") or "").strip()
    if message:
        return message
    reason_codes = entry.get("reason_codes")
    if isinstance(reason_codes, list):
        for reason_code in reason_codes:
            if reason_code == "large_vertical_gap":
                first = _target_text(entry.get("first"))
                second = _target_text(entry.get("second"))
                if first and second:
                    return f"{first}与{second}之间存在较大留白。"
            mapped_message = _LAYOUT_REASON_MESSAGES.get(str(reason_code))
            if mapped_message:
                return mapped_message
    return f"页面 {section} 检查发现需要关注的布局结果。"


def _layout_target(entry: Mapping[str, Any]) -> str | None:
    """从布局条目提取最短稳定定位信息。"""

    for field_name in ("target", "first", "element", "parent"):
        value = entry.get(field_name)
        target = _target_text(value)
        if target:
            return target
    return None


def _target_text(value: Any) -> str | None:
    """把浏览器目标或代码定位对象压缩为稳定短文本。"""

    if isinstance(value, str) and value.strip():
        return value.strip()
    if not isinstance(value, dict):
        return None
    label = str(value.get("label") or "").strip()
    locator = value.get("locator")
    locator_value = (
        str(locator.get("value") or "").strip()
        if isinstance(locator, dict)
        else ""
    )
    if label and locator_value:
        return f"{label} ({locator_value})"
    if label or locator_value:
        return label or locator_value
    return _location_text(value)


def _layout_facts(entry: Mapping[str, Any]) -> dict[str, Any]:
    """只保留布局条目中的小型数值 facts，不回传原始几何对象。"""

    return _compact_facts(entry) or {}


def _compact_facts(value: Any) -> dict[str, Any] | None:
    """从诊断 facts 中提取有界标量，丢弃 frame、root、nodes 等几何明细。"""

    if not isinstance(value, dict):
        return None
    facts: dict[str, Any] = {}
    for key in _FACT_KEYS:
        item = value.get(key)
        if isinstance(item, (str, int, float, bool)):
            facts[key] = item
    for key in ("nodes", "clipped"):
        item = value.get(key)
        if isinstance(item, list):
            facts[f"{key}_count"] = len(item)
    return facts or None


def _location_text(value: Mapping[str, Any]) -> str | None:
    """把编译诊断的文件、行列或 selector 定位压缩成一行。"""

    file_name = str(value.get("file") or value.get("path") or "").strip()
    line = value.get("line")
    column = value.get("column") or value.get("col")
    position = ""
    if line is not None:
        position = str(line)
        if column is not None:
            position += f":{column}"
    selector = str(value.get("selector") or value.get("value") or "").strip()
    if file_name and position:
        return f"{file_name}:{position}"
    if file_name:
        return file_name
    if selector and position:
        return f"{selector}（第 {position} 行）"
    if position:
        return f"第 {position} 行"
    return selector or None


def _deduplicate_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 severity、code、message 和定位去重，避免同一问题重复提示。"""

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for issue in issues:
        identity = (
            str(issue.get("severity") or ""),
            str(issue.get("code") or ""),
            str(issue.get("message") or ""),
            str(issue.get("target") or ""),
        )
        if identity in seen:
            continue
        seen.add(identity)
        result.append(issue)
    return result


def _resolve_status(result: Mapping[str, Any]) -> str:
    """统一完整校验结果的状态显示。"""

    status = str(result.get("status") or "").strip()
    if status in {"passed", "passed_with_warnings", "failed", "unavailable"}:
        return status
    if result.get("success") is True:
        return "passed"
    return "failed"


def _resolve_summary(
    result: Mapping[str, Any],
    *,
    resource_type: str,
    status: str,
    warning_count: int,
) -> str:
    """生成不重复原始诊断的短摘要，并统一无问题文案。"""

    summary = str(result.get("summary") or "").strip()
    if status == "passed_with_warnings" and warning_count and (
        not summary or ("警告" not in summary and "warning" not in summary.lower())
    ):
        return f"{_RESOURCE_LABELS.get(resource_type, resource_type)}代码检查通过，发现 {warning_count} 个警告。"
    if summary:
        return summary
    if status == "unavailable":
        return f"{_RESOURCE_LABELS.get(resource_type, resource_type)} Runtime 校验暂不可用。"
    if status == "passed":
        return f"{_RESOURCE_LABELS.get(resource_type, resource_type)}代码检查通过。"
    return f"{_RESOURCE_LABELS.get(resource_type, resource_type)}代码检查未通过。"


def _build_layout_summary(result: Mapping[str, Any], *, resource_type: str) -> str | None:
    """按页面布局检测类别聚合 actionable 条目数量。"""

    if resource_type != "page" or not isinstance(result.get("layout_analysis"), dict):
        return None
    counts: list[str] = []
    layout_analysis = result["layout_analysis"]
    for section in _PAGE_LAYOUT_SECTIONS:
        entries = layout_analysis.get(section)
        if not isinstance(entries, list):
            continue
        actionable_count = sum(
            isinstance(entry, dict) and entry.get("attention") in {"review", "likely_issue"}
            for entry in entries
        )
        if actionable_count:
            counts.append(f"{section}={actionable_count}")
    return "、".join(counts) if counts else None


def _build_scenario_summary(result: Mapping[str, Any]) -> str | None:
    """把组件的全量场景结果压缩为计数和异常场景名称。"""

    scenarios = result.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return None
    counts = {"passed": 0, "passed_with_warnings": 0, "failed": 0}
    abnormal: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        status = str(scenario.get("status") or "failed")
        if status not in counts:
            status = "failed"
        counts[status] += 1
        if status != "passed":
            abnormal.append(str(scenario.get("key") or "unknown"))
    total = sum(counts.values())
    suffix = f"；需关注：{', '.join(abnormal[:MAX_VALIDATION_ISSUES])}" if abnormal else ""
    return (
        f"已检查 {total} 个场景，通过 {counts['passed']} 个，"
        f"警告 {counts['passed_with_warnings']} 个，失败 {counts['failed']} 个{suffix}。"
    )


def _format_issue(issue: Mapping[str, Any], *, detail: bool) -> str:
    """把单条问题格式化为一行短文本。"""

    suffix: list[str] = []
    target = _target_text(issue.get("target"))
    if target:
        suffix.append(f"定位：{target}")
    if issue.get("scenario"):
        suffix.append(f"scenario={issue['scenario']}")
    if issue.get("profile"):
        suffix.append(f"profile={issue['profile']}")
    if detail:
        facts = issue.get("facts")
        if isinstance(facts, dict) and facts:
            suffix.append("facts=" + ", ".join(f"{key}={value}" for key, value in facts.items()))
    tail = f"（{'；'.join(suffix)}）" if suffix else ""
    return f"- [{issue['code']}] {issue['message']}{tail}"
