"""文件功能：验证成员助手委派运行的轻量工具函数，防止消息历史恢复链路回归。"""

from app.ai.member_delegation import _merge_member_message_history


def test_merge_member_message_history_should_filter_invalid_items() -> None:
    """成员消息历史合并应过滤非 dict 项，避免恢复运行时坏数据触发异常。"""

    base = [{"kind": "request", "parts": []}, "invalid"]  # type: ignore[list-item]
    latest = [{"kind": "request", "parts": []}, {"kind": "response", "parts": []}]

    assert _merge_member_message_history(base, latest) == latest


def test_merge_member_message_history_should_append_when_latest_not_prefix() -> None:
    """新消息不是完整快照时，应追加到既有成员历史后。"""

    base = [{"kind": "request", "parts": []}]
    latest = [{"kind": "response", "parts": []}]

    assert _merge_member_message_history(base, latest) == [*base, *latest]
