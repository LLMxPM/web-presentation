"""文件功能：验证历史压缩的 token 感知分块不会截断或损坏长文本。"""

from __future__ import annotations

import tiktoken
from pydantic_ai.messages import ModelRequest, UserPromptPart

from app.ai.history_compression import _history_json_text, _split_text_by_tokens


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


def test_history_json_text_should_keep_run_partition_metadata_for_compressor() -> None:
    """压缩器序列化历史时应保留应用侧分区 metadata。"""

    text = _history_json_text([
        ModelRequest(
            parts=[UserPromptPart(content="历史用户消息")],
            metadata={
                "run_id": "run-1",
                "workspace_id": 10,
                "project_id": 20,
                "page_id": 30,
                "allowed_projects": [{"id": 20, "name": "项目"}],
            },
        )
    ])

    assert '"run_id": "run-1"' in text
    assert '"workspace_id": 10' in text
    assert '"project_id": 20' in text
    assert '"page_id": 30' in text
    assert '"allowed_projects"' in text
