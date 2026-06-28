"""文件功能：验证成员助手委派运行的轻量工具函数，防止消息历史恢复链路回归。"""

from typing import Any

import pytest

from app.ai.member_delegation import _build_member_history_processors, _merge_member_message_history


class _FakeContextProcessor:
    """模拟上下文处理器，确保成员侧包装函数按单参数 messages 调用也能工作。"""

    def __init__(self) -> None:
        """初始化记录字段，用于断言包装函数传入的参数。"""

        self.seen_run_context: Any | None = None
        self.seen_messages: list[Any] | None = None

    async def process(self, run_context: Any | None, messages: list[Any]) -> list[Any]:
        """记录调用参数并原样返回消息列表。"""

        self.seen_run_context = run_context
        self.seen_messages = messages
        return messages


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


@pytest.mark.asyncio
async def test_build_member_history_processors_should_accept_messages_only() -> None:
    """成员历史处理器应适配 Pydantic AI 1.38 的单参数调用方式。"""

    context_processor = _FakeContextProcessor()
    messages = [{"kind": "request", "parts": []}]

    history_processor = _build_member_history_processors(context_processor)[0]  # type: ignore[arg-type]

    assert await history_processor(messages) == messages
    assert context_processor.seen_run_context is None
    assert context_processor.seen_messages is messages
