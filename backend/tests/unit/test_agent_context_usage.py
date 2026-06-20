"""文件功能：验证智能体上下文 usage 归一化规则。"""

from __future__ import annotations

from types import SimpleNamespace

from pydantic_ai.usage import RequestUsage

from app.ai.context_usage import usage_snapshot_from_messages, usage_snapshot_from_value


def test_usage_snapshot_from_pydantic_request_usage() -> None:
    """Pydantic RequestUsage 应按 input + output 作为上下文占用。"""

    snapshot = usage_snapshot_from_value(RequestUsage(input_tokens=120, output_tokens=30, details={"reasoning_tokens": 7}))

    assert snapshot.input_tokens == 120
    assert snapshot.output_tokens == 30
    assert snapshot.context_used_tokens == 150
    assert snapshot.reasoning_tokens == 7


def test_usage_snapshot_from_openai_compatible_usage() -> None:
    """OpenAI-compatible usage 字段应映射到统一字段。"""

    snapshot = usage_snapshot_from_value(
        {
            "prompt_tokens": 200,
            "completion_tokens": 40,
            "total_tokens": 240,
            "completion_tokens_details": {"reasoning_tokens": 11},
        }
    )

    assert snapshot.input_tokens == 200
    assert snapshot.output_tokens == 40
    assert snapshot.total_tokens == 240
    assert snapshot.reasoning_tokens == 11


def test_usage_snapshot_from_ollama_usage() -> None:
    """Ollama usage 指标应兼容 prompt_eval_count/eval_count。"""

    snapshot = usage_snapshot_from_value(SimpleNamespace(prompt_eval_count=80, eval_count=20))

    assert snapshot.input_tokens == 80
    assert snapshot.output_tokens == 20
    assert snapshot.total_tokens == 100


def test_usage_snapshot_from_messages_uses_latest_response() -> None:
    """消息历史中应取最后一次模型响应 usage，缺失 usage 视为 0。"""

    snapshot = usage_snapshot_from_messages(
        [
            {"kind": "response", "usage": {"input_tokens": 10, "output_tokens": 2}},
            {"kind": "request", "parts": []},
            {"kind": "response", "usage": {"prompt_tokens": 30, "completion_tokens": 5}},
        ]
    )
    missing = usage_snapshot_from_messages([{"kind": "response", "parts": []}])

    assert snapshot.context_used_tokens == 35
    assert missing.context_used_tokens == 0
