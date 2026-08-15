"""文件功能：验证历史压缩不再分块，并保持结构化输入的完整语义。"""

from __future__ import annotations

from pydantic_ai.messages import ModelRequest, UserPromptPart

from app.ai.history_compression import build_deterministic_summary
from app.ai.history_compression_input import build_local_compression_input


def test_deterministic_summary_should_keep_unicode_content_without_chunking() -> None:
    """确定性摘要应直接消费结构化输入，不依赖历史文本分块。"""

    source = ("中文历史🙂工具调用完成。" * 80) + "最终约束"
    messages = [ModelRequest(parts=[UserPromptPart(content=source)])]
    summary = build_deterministic_summary(messages, existing_summary=None, target_tokens=2_000)

    assert source in summary
    assert "�" not in summary


def test_structured_compression_input_should_not_split_one_message() -> None:
    """单条长消息在结构化输入中保持一个事实项，而不是切成多个 JSON 片段。"""

    result = build_local_compression_input(
        [ModelRequest(parts=[UserPromptPart(content="history item with stable token boundaries\n" * 100)])]
    )

    message_items = [item for item in result.payload["items"] if item["kind"] == "user_message"]
    assert len(message_items) == 1
    assert result.stats.normalized_item_count == 1


def test_structured_compression_input_should_keep_run_partition_metadata() -> None:
    """结构化输入应保留应用侧分区 metadata。"""

    result = build_local_compression_input([
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
    context = next(item for item in result.payload["items"] if item["kind"] == "run_context")

    assert context["run_id"] == "run-1"
    assert context["workspace_id"] == 10
    assert context["project_id"] == 20
    assert context["page_id"] == 30
    assert context["allowed_projects"]
