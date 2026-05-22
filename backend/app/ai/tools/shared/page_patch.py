"""文件功能：提供页面源码统一 Diff 生成与 Unified Diff 应用能力。"""

from __future__ import annotations

import re
from difflib import unified_diff

from app.ai.tools.shared.page_patch_matching import (
    lines_match_with_optional_trailing_lf,
    preserve_actual_line_ending,
    preview_patch_line,
)
from app.ai.tools.shared.page_patch_repair import PatchApplyResult, apply_relocated_unified_diff, parse_unified_diff_hunks
from app.core.text_normalizer import normalize_text_to_lf
from app.core.exceptions import AppException

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


def build_unified_diff(current_content: str, new_content: str) -> str:
    """生成当前内容与目标内容的统一 diff。"""

    return "".join(
        unified_diff(
            normalize_text_to_lf(current_content).splitlines(keepends=True),
            normalize_text_to_lf(new_content).splitlines(keepends=True),
            fromfile="current",
            tofile="proposed",
        )
    )


def apply_unified_diff(current_content: str, unified_patch: str) -> str:
    """将 unified diff 应用到当前页面源码；仅支持标准文本 patch。"""

    normalized_patch = normalize_text_to_lf(unified_patch)
    if not normalized_patch.strip():
        raise AppException(status_code=400, code="AI_PAGE_DIFF_EMPTY", detail="Unified Diff 不能为空。")

    patch_lines = normalized_patch.splitlines(keepends=True)
    hunk_indices = [index for index, line in enumerate(patch_lines) if line.startswith("@@ ")]
    if not hunk_indices:
        raise AppException(status_code=400, code="AI_PAGE_DIFF_INVALID", detail="Unified Diff 缺少 hunk 头，无法应用。")

    source_lines = normalize_text_to_lf(current_content).splitlines(keepends=True)
    result_lines: list[str] = []
    source_index = 0

    for hunk_position, hunk_start in enumerate(hunk_indices):
        header_match = _HUNK_HEADER_RE.match(patch_lines[hunk_start].rstrip("\n"))
        if header_match is None:
            raise AppException(status_code=400, code="AI_PAGE_DIFF_INVALID", detail="Unified Diff hunk 头格式不合法。")

        old_start = int(header_match.group("old_start"))
        target_index = max(old_start - 1, 0)
        current_old_line_no = old_start
        if target_index < source_index:
            raise AppException(status_code=400, code="AI_PAGE_DIFF_INVALID", detail="Unified Diff hunk 顺序不合法。")

        result_lines.extend(source_lines[source_index:target_index])
        source_index = target_index

        hunk_end = hunk_indices[hunk_position + 1] if hunk_position + 1 < len(hunk_indices) else len(patch_lines)
        for line in patch_lines[hunk_start + 1 : hunk_end]:
            if not line:
                continue
            marker = line[0]
            payload = line[1:]
            if marker == " ":
                _assert_source_line_matches(
                    source_lines,
                    source_index,
                    payload,
                    hunk_no=hunk_position + 1,
                    source_line_no=current_old_line_no,
                )
                result_lines.append(preserve_actual_line_ending(payload, source_lines[source_index]))
                source_index += 1
                current_old_line_no += 1
            elif marker == "-":
                _assert_source_line_matches(
                    source_lines,
                    source_index,
                    payload,
                    hunk_no=hunk_position + 1,
                    source_line_no=current_old_line_no,
                )
                source_index += 1
                current_old_line_no += 1
            elif marker == "+":
                result_lines.append(payload)
            elif marker == "\\":
                continue
            else:
                raise AppException(status_code=400, code="AI_PAGE_DIFF_INVALID", detail="Unified Diff 包含无法识别的行前缀。")

    result_lines.extend(source_lines[source_index:])
    return "".join(result_lines)


def apply_unified_diff_with_repair(current_content: str, unified_patch: str) -> PatchApplyResult:
    """先按严格模式应用 patch，失败后再尝试按旧内容窗口重定位。"""

    normalized_current_content = normalize_text_to_lf(current_content)
    normalized_patch = normalize_text_to_lf(unified_patch)

    try:
        next_content = apply_unified_diff(normalized_current_content, normalized_patch)
        return PatchApplyResult(
            next_content=next_content,
            canonical_diff=build_unified_diff(normalized_current_content, next_content),
            repaired=False,
        )
    except AppException as exc:
        if exc.code != "AI_PAGE_DIFF_CONFLICT":
            raise

        try:
            parsed_hunks = parse_unified_diff_hunks(normalized_patch, _HUNK_HEADER_RE)
            next_content = apply_relocated_unified_diff(normalized_current_content, parsed_hunks)
        except AppException as repair_exc:
            raise AppException(
                status_code=409,
                code="AI_PAGE_DIFF_CONFLICT",
                detail=f"{exc.detail} 自动重定位失败：{repair_exc.detail}",
            ) from repair_exc

        return PatchApplyResult(
            next_content=next_content,
            canonical_diff=build_unified_diff(normalized_current_content, next_content),
            repaired=True,
        )


def _assert_source_line_matches(
    source_lines: list[str],
    source_index: int,
    expected_line: str,
    *,
    hunk_no: int,
    source_line_no: int,
) -> None:
    """校验 patch 当前行是否与待修改源码严格一致。"""

    if source_index >= len(source_lines):
        raise AppException(
            status_code=409,
            code="AI_PAGE_DIFF_CONFLICT",
            detail=(
                "Unified Diff 无法应用：源码长度不匹配。"
                f" hunk #{hunk_no} 期望读取第 {source_line_no} 行，"
                f"但当前源码只剩 {len(source_lines)} 行。"
            ),
        )
    actual_line = source_lines[source_index]
    if not lines_match_with_optional_trailing_lf(expected_line, actual_line):
        raise AppException(
            status_code=409,
            code="AI_PAGE_DIFF_CONFLICT",
            detail=(
                "Unified Diff 无法应用：上下文内容不匹配。"
                f" hunk #{hunk_no} 第 {source_line_no} 行"
                f" 期望 {preview_patch_line(expected_line)}，"
                f"实际为 {preview_patch_line(actual_line)}。"
            ),
        )
