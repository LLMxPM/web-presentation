"""文件功能：验证智能体结构化源码 edits 引擎的匹配、插入和错误保护规则。"""

from app.ai.tools.shared.source_edits import ReplaceExactEdit, apply_source_edits, calculate_source_hash
from app.core.exceptions import AppException


def test_source_edits_should_replace_and_generate_canonical_diff() -> None:
    """唯一命中 old_text 时应替换源码并生成展示 diff。"""

    result = apply_source_edits(
        "alpha\nbeta\ngamma\n",
        [{"type": "replace_exact", "old_text": "beta\n", "new_text": "zeta\n"}],
    )

    assert result.next_content == "alpha\nzeta\ngamma\n"
    assert result.applied_edit_count == 1
    assert "-beta\n+zeta\n" in result.canonical_diff


def test_source_edits_should_insert_after_unique_anchor() -> None:
    """唯一命中 anchor_text 时应在锚点后插入内容。"""

    result = apply_source_edits(
        "<template>\n</template>\n",
        [{"type": "insert_after", "anchor_text": "<template>\n", "new_text": "  <main />\n"}],
    )

    assert result.next_content == "<template>\n  <main />\n</template>\n"


def test_source_edits_should_accept_pydantic_edit_payload() -> None:
    """工具 schema 使用的 Pydantic edit 对象也应能被应用引擎处理。"""

    result = apply_source_edits(
        "alpha\nbeta\n",
        [ReplaceExactEdit(type="replace_exact", old_text="beta\n", new_text="zeta\n")],
    )

    assert result.next_content == "alpha\nzeta\n"


def test_source_edits_should_reject_ambiguous_match() -> None:
    """多处命中的精确替换应拒绝，避免漂移到错误位置。"""

    try:
        apply_source_edits(
            "same\nsame\n",
            [{"type": "replace_exact", "old_text": "same\n", "new_text": "next\n"}],
        )
    except AppException as exc:
        assert exc.code == "AI_SOURCE_EDIT_AMBIGUOUS"
    else:
        raise AssertionError("多处命中的 old_text 应被拒绝。")


def test_source_hash_should_ignore_crlf_difference() -> None:
    """草稿 hash 应基于 LF 归一化结果生成。"""

    assert calculate_source_hash("a\r\nb\r\n") == calculate_source_hash("a\nb\n")
