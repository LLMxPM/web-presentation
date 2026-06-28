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


def test_trim_unprocessed_tool_call_history_should_drop_orphan_tool_return() -> None:
    """历史开头残留孤立 tool-return 时，应移除该请求并保留后续助手文本。"""

    history = [
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "update_project_route_tree",
                    "content": {"ok": True},
                    "tool_call_id": "call-route",
                }
            ],
        },
        {"kind": "response", "parts": [{"part_kind": "text", "content": "路由已更新。"}]},
    ]

    assert trim_unprocessed_tool_call_history(history) == history[1:]


def test_trim_unprocessed_tool_call_history_should_keep_consecutive_tool_returns() -> None:
    """deferred 恢复会产生连续 tool-return request，应按同一组 tool-call 继续配对。"""

    history = [
        {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": "更新页面"}]},
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "update_page_metadata",
                    "args": "{}",
                    "tool_call_id": "call-metadata",
                },
                {
                    "part_kind": "tool-call",
                    "tool_name": "update_project_route_tree",
                    "args": "{}",
                    "tool_call_id": "call-route",
                },
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "update_page_metadata",
                    "content": "页面元数据已更新",
                    "tool_call_id": "call-metadata",
                }
            ],
        },
        {
            "kind": "request",
            "parts": [
                {
                    "part_kind": "tool-return",
                    "tool_name": "update_project_route_tree",
                    "content": "路由已更新",
                    "tool_call_id": "call-route",
                },
                {"part_kind": "user-prompt", "content": ""},
            ],
        },
        {"kind": "response", "parts": [{"part_kind": "text", "content": "完成。"}]},
    ]

    assert trim_unprocessed_tool_call_history(history) == history
