"""文件功能：验证成员助手委派结果的文本提取规则。"""

from __future__ import annotations

from app.ai.member_delegation import _latest_member_response_text


def test_latest_member_response_text_should_use_last_response_text() -> None:
    """成员委派返回结果应取最后一条模型回复，而不是累计所有流式文本。"""

    messages = [
        {
            "kind": "request",
            "parts": [{"part_kind": "user-prompt", "content": "整理资源。"}],
        },
        {
            "kind": "response",
            "parts": [{"part_kind": "text", "content": "先读取资源列表。"}],
        },
        {
            "kind": "request",
            "parts": [{"part_kind": "tool-return", "content": {"total": 2}}],
        },
        {
            "kind": "response",
            "parts": [
                {"part_kind": "text", "content": "资源整理完成。"},
                {"part_kind": "tool-call", "content": "不应读取"},
            ],
        },
    ]

    assert _latest_member_response_text(messages) == "资源整理完成。"


def test_latest_member_response_text_should_join_text_parts_in_same_response() -> None:
    """同一条最终回复内存在多个文本 part 时，应按段落拼接。"""

    messages = [
        {
            "kind": "response",
            "parts": [
                {"part_kind": "text", "content": "第一段"},
                {"part_kind": "text", "content": "第二段"},
            ],
        }
    ]

    assert _latest_member_response_text(messages) == "第一段\n\n第二段"
