"""文件功能：提供 Unified Diff 行匹配与错误展示的公共辅助能力。"""

from __future__ import annotations


def lines_match_with_optional_trailing_lf(expected_line: str, actual_line: str) -> bool:
    """判断两行是否一致，允许仅在单个尾随 LF 上存在差异。"""

    if expected_line == actual_line:
        return True

    expected_body, expected_has_lf = _split_trailing_lf(expected_line)
    actual_body, actual_has_lf = _split_trailing_lf(actual_line)
    return expected_body == actual_body and expected_has_lf != actual_has_lf


def line_sequences_match_with_optional_trailing_lf(expected_lines: list[str], actual_lines: list[str]) -> bool:
    """判断两组行是否逐行一致，允许每行仅在单个尾随 LF 上存在差异。"""

    if len(expected_lines) != len(actual_lines):
        return False
    return all(
        lines_match_with_optional_trailing_lf(expected_line, actual_line)
        for expected_line, actual_line in zip(expected_lines, actual_lines, strict=True)
    )


def preview_patch_line(line: str, limit: int = 80) -> str:
    """将行内容压缩为单行预览，同时保留尾随 LF 差异。"""

    rendered = repr(line)
    if len(rendered) <= limit:
        return rendered
    return repr(f"{line[: max(limit - 3, 0)]}...")


def preserve_actual_line_ending(expected_line: str, actual_line: str) -> str:
    """在正文一致时优先沿用源码中的尾随 LF，避免 patch 末行丢失换行。"""

    if expected_line == actual_line:
        return expected_line

    expected_body, _ = _split_trailing_lf(expected_line)
    actual_body, actual_has_lf = _split_trailing_lf(actual_line)
    if expected_body == actual_body and actual_has_lf:
        return f"{expected_body}\n"
    return expected_line


def _split_trailing_lf(line: str) -> tuple[str, bool]:
    """拆分行正文与是否带尾随 LF 标记。"""

    if line.endswith("\n"):
        return line[:-1], True
    return line, False
