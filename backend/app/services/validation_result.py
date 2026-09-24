"""文件功能：提供页面/组件校验结果的单一通过判定谓词，统一跨阶段写入语义。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.page_render_diagnostics_service import PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE

# 阻断状态：阶段或顶层命中即不得视为通过
_BLOCKING_STATUSES = frozenset({"failed", "unavailable"})
# 阶段级可通过状态；skipped 表示该阶段未执行，不阻断其它阶段结论
_STAGE_PASSING_STATUSES = frozenset({"passed", "passed_with_warnings", "warning", "skipped"})
# 顶层可通过状态；不含 skipped——顶层「未执行」不得视为通过
_RESULT_PASSING_STATUSES = frozenset({"passed", "passed_with_warnings", "warning"})


def is_validation_passed(
    result: Mapping[str, Any] | None,
    *,
    require_render: bool = True,
) -> bool:
    """判断校验结果是否允许写入。

    页面写入默认 require_render=True：render 阶段 unavailable/failed 不得视为通过，
    与 docs/developer 中「执行不可用不能映射为检查通过」的契约一致。
    组件只做契约 + 编译，调用方应传 require_render=False；此时顶层 status/success
    反映的是「整体未完成」，不得用它否决已通过的编译阶段。
    """

    if not isinstance(result, Mapping):
        return False

    raw_stages = result.get("stages")
    stages: Mapping[str, Any] = raw_stages if isinstance(raw_stages, Mapping) else {}
    compile_status = stages.get("compile")
    render_status = stages.get("render")
    status = result.get("status")

    if compile_status is not None or render_status is not None:
        if compile_status is not None and compile_status not in _STAGE_PASSING_STATUSES:
            return False
        if not require_render:
            # 只判编译：无编译阶段结论时不得放行。
            return compile_status in _STAGE_PASSING_STATUSES
        if render_status is not None and render_status not in _STAGE_PASSING_STATUSES:
            return False
        return status not in _BLOCKING_STATUSES

    if status in _BLOCKING_STATUSES:
        return False
    return result.get("success") is True or status in _RESULT_PASSING_STATUSES


def is_render_unavailable(result: Mapping[str, Any] | None) -> bool:
    """判断结果是否处于渲染执行不可用（基础设施故障，非内容错误）。"""

    if not isinstance(result, Mapping):
        return False
    raw_stages = result.get("stages")
    stages: Mapping[str, Any] = raw_stages if isinstance(raw_stages, Mapping) else {}
    if stages.get("render") == "unavailable":
        return True
    return result.get("status") == "unavailable" and stages.get("compile") not in _BLOCKING_STATUSES


def resolve_validation_error_code(result: Mapping[str, Any] | None, *, fallback: str) -> str:
    """解析校验失败错误码；渲染执行不可用不得复用内容错误码，否则调用方无法重试。"""

    if is_render_unavailable(result):
        return PAGE_RENDER_DIAGNOSTICS_UNAVAILABLE_CODE
    return fallback


def resolve_write_gate(
    result: Mapping[str, Any] | None,
    *,
    skip_visual_verification: bool = False,
) -> tuple[bool, bool]:
    """返回 (是否允许写入, 是否跳过了视觉校验)。

    默认 render unavailable 拒写；skip_visual_verification=True 且编译已通过时允许写入，
    调用方必须在 job result 与 AI 事件中留下 skipped_visual_verification 审计标记。
    """

    if is_validation_passed(result, require_render=True):
        return True, False
    if (
        skip_visual_verification
        and is_render_unavailable(result)
        and is_validation_passed(result, require_render=False)
    ):
        return True, True
    return False, False
