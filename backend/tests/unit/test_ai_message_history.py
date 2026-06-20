"""文件功能：验证 Agent 消息历史清理逻辑，避免失败 run 留下未闭合工具调用。"""

from __future__ import annotations

from app.ai.message_history import trim_unprocessed_tool_call_history


def test_trim_unprocessed_tool_call_history_should_keep_closed_tool_call() -> None:
    """已有 tool-return 配对时不应裁剪历史。"""

    history = [
        {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "读取页面"}]},
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "get_page_content",
                    "args": "{}",
                    "tool_call_id": "call-read",
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "get_page_content",
                    "content": "页面源码",
                    "tool_call_id": "call-read",
                }
            ],
        },
    ]

    assert trim_unprocessed_tool_call_history(history) == history


def test_trim_unprocessed_tool_call_history_should_drop_open_tail() -> None:
    """终态失败 run 尾部仍有 tool-call 时，应从该响应开始裁掉。"""

    history = [
        {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "读取截图"}]},
        {
            "kind": "response",
            "parts": [
                {"part_kind": "text", "content": "我先看截图。"},
                {
                    "part_kind": "tool-call",
                    "tool_name": "get_page_screenshot",
                    "args": '{"page_id": 22}',
                    "tool_call_id": "call-shot",
                },
            ],
        },
    ]

    assert trim_unprocessed_tool_call_history(history) == history[:1]
