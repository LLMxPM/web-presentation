"""文件功能：验证历史压缩的 token 感知分块不会截断或损坏长文本。"""

from __future__ import annotations

import tiktoken

from app.ai.history_compression import _split_text_by_tokens


def test_split_text_by_tokens_should_preserve_unicode_content() -> None:
    """跨 token 的中文与 Emoji 在分块后仍应逐字还原。"""

    source = ("中文历史🙂工具调用完成。" * 80) + "最终约束"
    chunks = _split_text_by_tokens(source, max_tokens=17)

    assert len(chunks) > 1
    assert "".join(chunks) == source
    assert "�" not in "".join(chunks)


def test_split_text_by_tokens_should_respect_token_sized_chunks() -> None:
    """普通文本分块应保持在指定 token 尺寸内。"""

    encoding = tiktoken.get_encoding("cl100k_base")
    source = "history item with stable token boundaries\n" * 100
    chunks = _split_text_by_tokens(source, max_tokens=32)

    assert "".join(chunks) == source
    assert all(len(encoding.encode(chunk)) <= 32 for chunk in chunks)
