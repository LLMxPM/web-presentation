"""文件功能：归一化不同模型供应商返回的 token usage，并生成上下文占用快照。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class AgentContextUsageSnapshot:
    """描述一次模型调用后可用于上下文高水位判断的真实 usage。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def context_used_tokens(self) -> int:
        """返回下一次请求会继承的上下文占用，按 input + output 计算。"""

        return max(0, self.input_tokens) + max(0, self.output_tokens)


def usage_snapshot_from_messages(messages: list[dict[str, Any]] | None) -> AgentContextUsageSnapshot:
    """从序列化消息历史中提取最后一次模型响应 usage；缺失时返回 0。"""

    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        snapshot = usage_snapshot_from_value(message.get("usage"))
        if snapshot.context_used_tokens > 0 or snapshot.total_tokens > 0:
            return snapshot
        provider_details = message.get("provider_details")
        if isinstance(provider_details, dict):
            snapshot = usage_snapshot_from_value(provider_details.get("usage"))
            if snapshot.context_used_tokens > 0 or snapshot.total_tokens > 0:
                return snapshot
    return AgentContextUsageSnapshot()


def usage_snapshot_from_value(value: Any) -> AgentContextUsageSnapshot:
    """把 Pydantic、OpenAI-compatible、Ollama 等 usage 形态归一化。"""

    if value is None:
        return AgentContextUsageSnapshot()
    input_tokens = _first_int(value, ("input_tokens", "request_tokens", "prompt_tokens", "prompt_eval_count"))
    output_tokens = _first_int(value, ("output_tokens", "response_tokens", "completion_tokens", "eval_count"))
    total_tokens = _first_int(value, ("total_tokens",))
    details = _first_mapping(value, ("details", "output_tokens_details", "completion_tokens_details"))
    reasoning_tokens = _first_int(details, ("reasoning_tokens",)) if details is not None else 0
    if reasoning_tokens == 0:
        reasoning_tokens = _first_int(value, ("reasoning_tokens",))
    if total_tokens <= 0 and (input_tokens > 0 or output_tokens > 0):
        total_tokens = input_tokens + output_tokens
    return AgentContextUsageSnapshot(
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        total_tokens=max(0, total_tokens),
        reasoning_tokens=max(0, reasoning_tokens),
    )


def _first_int(value: Any, keys: tuple[str, ...]) -> int:
    """按候选字段顺序读取整数；字段不存在或不可转为整数时返回 0。"""

    for key in keys:
        raw = _get_value(value, key)
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0


def _first_mapping(value: Any, keys: tuple[str, ...]) -> Any | None:
    """按候选字段顺序读取 dict 或对象明细。"""

    for key in keys:
        raw = _get_value(value, key)
        if isinstance(raw, dict) or raw is not None and not isinstance(raw, (str, int, float, bool)):
            return raw
    return None


def _get_value(value: Any, key: str) -> Any:
    """兼容 dict 和对象属性读取 usage 字段。"""

    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
