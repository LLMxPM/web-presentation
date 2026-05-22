"""文件功能：为轻微错位的 Unified Diff 提供重定位与 canonical diff 重建能力。"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.tools.shared.page_patch_matching import (
    line_sequences_match_with_optional_trailing_lf,
    lines_match_with_optional_trailing_lf,
    preserve_actual_line_ending,
)
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf


@dataclass(slots=True, frozen=True)
class PatchApplyResult:
    """描述一次 patch 应用的结果，包含新源码与 canonical diff。"""

    next_content: str
    canonical_diff: str
    repaired: bool = False


@dataclass(slots=True, frozen=True)
class ParsedUnifiedDiffHunk:
    """表示一个已解析的 unified diff hunk。"""

    old_start: int
    new_start: int
    body_lines: list[str]


def apply_relocated_unified_diff(
    current_content: str,
    hunks: list[ParsedUnifiedDiffHunk],
) -> str:
    """基于 hunk 正文内容在当前源码中重定位并应用 patch。"""

    source_lines = normalize_text_to_lf(current_content).splitlines(keepends=True)
    result_lines: list[str] = []
    source_index = 0

    for hunk_no, hunk in enumerate(hunks, start=1):
        old_lines = _extract_old_lines(hunk.body_lines)
        if not old_lines:
            raise AppException(
                status_code=409,
                code="AI_PAGE_DIFF_REPAIR_FAILED",
                detail=f"自动重定位失败：hunk #{hunk_no} 不包含可用于定位的旧内容。",
            )

        expected_index = max(hunk.old_start - 1, source_index)
        candidate_indexes = _find_matching_windows(source_lines, old_lines, min_index=source_index)
        target_index = _select_relocation_index(
            candidate_indexes,
            expected_index=expected_index,
            hunk_no=hunk_no,
        )

        result_lines.extend(source_lines[source_index:target_index])
        source_index = target_index

        for line in hunk.body_lines:
            if not line:
                continue
            marker = line[0]
            payload = line[1:]
            if marker == " ":
                _assert_relocated_line_matches(
                    source_lines,
                    source_index,
                    payload,
                    hunk_no=hunk_no,
                )
                result_lines.append(preserve_actual_line_ending(payload, source_lines[source_index]))
                source_index += 1
            elif marker == "-":
                _assert_relocated_line_matches(
                    source_lines,
                    source_index,
                    payload,
                    hunk_no=hunk_no,
                )
                source_index += 1
            elif marker == "+":
                result_lines.append(payload)
            elif marker == "\\":
                continue
            else:
                raise AppException(
                    status_code=400,
                    code="AI_PAGE_DIFF_INVALID",
                    detail="Unified Diff 包含无法识别的行前缀。",
                )

    result_lines.extend(source_lines[source_index:])
    return "".join(result_lines)


def parse_unified_diff_hunks(
    unified_patch: str,
    header_pattern,
) -> list[ParsedUnifiedDiffHunk]:
    """解析 unified diff 中的 hunk 结构，供重定位逻辑复用。"""

    normalized_patch = normalize_text_to_lf(unified_patch)
    patch_lines = normalized_patch.splitlines(keepends=True)
    hunk_indices = [index for index, line in enumerate(patch_lines) if line.startswith("@@ ")]
    if not hunk_indices:
        raise AppException(status_code=400, code="AI_PAGE_DIFF_INVALID", detail="Unified Diff 缺少 hunk 头，无法应用。")

    parsed_hunks: list[ParsedUnifiedDiffHunk] = []
    for hunk_position, hunk_start in enumerate(hunk_indices):
        header_match = header_pattern.match(patch_lines[hunk_start].rstrip("\n"))
        if header_match is None:
            raise AppException(status_code=400, code="AI_PAGE_DIFF_INVALID", detail="Unified Diff hunk 头格式不合法。")
        hunk_end = hunk_indices[hunk_position + 1] if hunk_position + 1 < len(hunk_indices) else len(patch_lines)
        parsed_hunks.append(
            ParsedUnifiedDiffHunk(
                old_start=int(header_match.group("old_start")),
                new_start=int(header_match.group("new_start")),
                body_lines=patch_lines[hunk_start + 1 : hunk_end],
            )
        )
    return parsed_hunks


def _extract_old_lines(body_lines: list[str]) -> list[str]:
    """提取 hunk 中用于匹配旧源码窗口的上下文行与删除行。"""

    return [line[1:] for line in body_lines if line and line[0] in {" ", "-"}]


def _find_matching_windows(source_lines: list[str], old_lines: list[str], *, min_index: int) -> list[int]:
    """在当前源码中搜索与 hunk 旧内容完全一致的窗口。"""

    if not old_lines:
        return []

    match_indexes: list[int] = []
    window_size = len(old_lines)
    max_start = len(source_lines) - window_size
    for start_index in range(min_index, max_start + 1):
        if line_sequences_match_with_optional_trailing_lf(
            old_lines,
            source_lines[start_index : start_index + window_size],
        ):
            match_indexes.append(start_index)
    return match_indexes


def _select_relocation_index(
    candidate_indexes: list[int],
    *,
    expected_index: int,
    hunk_no: int,
    max_offset: int = 12,
) -> int:
    """从候选匹配窗口中选择一个安全的重定位位置。"""

    if not candidate_indexes:
        raise AppException(
            status_code=409,
            code="AI_PAGE_DIFF_REPAIR_FAILED",
            detail=f"自动重定位失败：hunk #{hunk_no} 未找到与旧内容完全一致的源码窗口。",
        )

    if expected_index in candidate_indexes:
        return expected_index

    nearby_matches = [index for index in candidate_indexes if abs(index - expected_index) <= max_offset]
    if len(nearby_matches) == 1:
        return nearby_matches[0]

    if len(candidate_indexes) == 1:
        return candidate_indexes[0]

    raise AppException(
        status_code=409,
        code="AI_PAGE_DIFF_REPAIR_FAILED",
        detail=(
            f"自动重定位失败：hunk #{hunk_no} 命中多个候选位置，"
            "无法安全判断应应用到哪一段源码。"
        ),
    )


def _assert_relocated_line_matches(
    source_lines: list[str],
    source_index: int,
    expected_line: str,
    *,
    hunk_no: int,
) -> None:
    """在重定位后再次校验旧内容，确保应用位置没有发生漂移。"""

    if source_index >= len(source_lines):
        raise AppException(
            status_code=409,
            code="AI_PAGE_DIFF_REPAIR_FAILED",
            detail=f"自动重定位失败：hunk #{hunk_no} 超出了当前源码范围。",
        )
    if not lines_match_with_optional_trailing_lf(expected_line, source_lines[source_index]):
        raise AppException(
            status_code=409,
            code="AI_PAGE_DIFF_REPAIR_FAILED",
            detail=f"自动重定位失败：hunk #{hunk_no} 在重定位后仍无法匹配旧内容。",
        )
