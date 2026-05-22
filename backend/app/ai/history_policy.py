"""文件功能：根据模型上下文配置与会话历史估算压缩和历史注入策略。"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Any

DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000
DEFAULT_MAX_OUTPUT_TOKENS = 32_000
DEFAULT_HISTORY_TOKEN_RATIO = 0.5
DEFAULT_COMPRESSION_TARGET_RATIO = 0.1
DEFAULT_MAX_TOOL_CALLS_FROM_HISTORY = 4
APPROX_TOKENS_PER_HISTORY_MESSAGE = 350
MIN_SAFETY_MARGIN_TOKENS = 512
SAFETY_MARGIN_RATIO = 0.08


@dataclass(slots=True, frozen=True)
class AgentHistoryPolicy:
    """描述一次 Agent 构建时的历史预算、压缩状态与历史注入参数。"""

    num_history_messages: int
    max_tool_calls_from_history: int = DEFAULT_MAX_TOOL_CALLS_FROM_HISTORY
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    history_token_ratio: float = DEFAULT_HISTORY_TOKEN_RATIO
    compression_target_ratio: float = DEFAULT_COMPRESSION_TARGET_RATIO
    safety_margin_tokens: int = 0
    current_input_tokens: int = 0
    fixed_context_tokens: int = 0
    history_budget_tokens: int = 0
    compression_target_tokens: int = 0
    estimated_history_tokens: int = 0
    estimated_summary_tokens: int = 0
    retained_recent_history_tokens: int = 0
    compression_required: bool = False
    summary_available: bool = False


def build_history_policy(
    model_config: Any,
    *,
    current_input: str | None = None,
    fixed_context_tokens: int = 0,
    history_messages: list[Any] | None = None,
    session_summary: Any | None = None,
) -> AgentHistoryPolicy:
    """按模型窗口、当前输入、固定上下文和历史 token 预算计算注入策略。"""

    context_window_tokens = _positive_int(
        getattr(model_config, "context_window_tokens", None),
        DEFAULT_CONTEXT_WINDOW_TOKENS,
    )
    max_output_tokens = _positive_int(
        getattr(model_config, "max_output_tokens", None),
        DEFAULT_MAX_OUTPUT_TOKENS,
    )
    history_token_ratio = _bounded_float(
        getattr(model_config, "history_token_ratio", None),
        DEFAULT_HISTORY_TOKEN_RATIO,
        lower=0.0,
        upper=0.9,
    )
    compression_target_ratio = _bounded_float(
        getattr(model_config, "compression_target_ratio", None),
        DEFAULT_COMPRESSION_TARGET_RATIO,
        lower=0.02,
        upper=0.5,
    )
    input_tokens = estimate_text_tokens(current_input or "")
    normalized_fixed_context_tokens = max(0, int(fixed_context_tokens or 0))
    safety_margin_tokens = max(MIN_SAFETY_MARGIN_TOKENS, ceil(context_window_tokens * SAFETY_MARGIN_RATIO))
    available_tokens = (
        context_window_tokens
        - max_output_tokens
        - input_tokens
        - normalized_fixed_context_tokens
        - safety_margin_tokens
    )
    history_budget = min(floor(context_window_tokens * history_token_ratio), max(0, available_tokens))
    compression_target = min(floor(context_window_tokens * compression_target_ratio), history_budget)

    message_token_pairs = _estimate_history_message_tokens(history_messages or [])
    summary_tokens = _estimate_summary_tokens(session_summary)
    message_tokens = sum(token_count for _, token_count in message_token_pairs)
    estimated_history_tokens = summary_tokens + message_tokens
    compression_required = estimated_history_tokens > history_budget
    target_recent_budget = max(0, (compression_target if compression_required else history_budget) - summary_tokens)
    retained_message_count, retained_history_tokens = _count_recent_messages_within_budget(
        message_token_pairs,
        target_recent_budget,
    )
    if not message_token_pairs and history_budget > 0:
        retained_message_count = max(0, floor(target_recent_budget / APPROX_TOKENS_PER_HISTORY_MESSAGE))
        retained_history_tokens = min(target_recent_budget, retained_message_count * APPROX_TOKENS_PER_HISTORY_MESSAGE)

    return AgentHistoryPolicy(
        num_history_messages=retained_message_count,
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        history_token_ratio=history_token_ratio,
        compression_target_ratio=compression_target_ratio,
        safety_margin_tokens=safety_margin_tokens,
        current_input_tokens=input_tokens,
        fixed_context_tokens=normalized_fixed_context_tokens,
        history_budget_tokens=history_budget,
        compression_target_tokens=compression_target,
        estimated_history_tokens=estimated_history_tokens,
        estimated_summary_tokens=summary_tokens,
        retained_recent_history_tokens=retained_history_tokens,
        compression_required=compression_required,
        summary_available=summary_tokens > 0,
    )


def estimate_text_tokens(text: str) -> int:
    """用偏保守的字符比例估算当前输入 token 数，避免依赖具体 tokenizer。"""

    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, ceil(len(stripped) / 3))


def _estimate_history_message_tokens(messages: list[Any]) -> list[tuple[Any, int]]:
    """估算历史消息 token；工具消息只保留关键结构，避免大结果主导预算。"""

    result: list[tuple[Any, int]] = []
    for message in messages:
        role = str(getattr(message, "role", "") or "").lower()
        if role == "system":
            continue
        content = getattr(message, "content", None)
        token_source = _stringify_for_estimation(content)
        if role == "tool":
            tool_payload = {
                "tool_name": getattr(message, "tool_name", None),
                "tool_call_id": getattr(message, "tool_call_id", None),
                "tool_args": getattr(message, "tool_args", None),
                "tool_call_error": getattr(message, "tool_call_error", None),
                "content": _truncate_text(token_source, 1200),
            }
            token_source = _stringify_for_estimation(tool_payload)
        result.append((message, estimate_text_tokens(token_source)))
    return result


def _estimate_summary_tokens(session_summary: Any | None) -> int:
    """估算 Agno 会话摘要 token。"""

    if session_summary is None:
        return 0
    if isinstance(session_summary, dict):
        summary_text = session_summary.get("summary")
        topics = session_summary.get("topics")
    else:
        summary_text = getattr(session_summary, "summary", None)
        topics = getattr(session_summary, "topics", None)
    return estimate_text_tokens(_stringify_for_estimation({"summary": summary_text, "topics": topics}))


def _count_recent_messages_within_budget(message_token_pairs: list[tuple[Any, int]], token_budget: int) -> tuple[int, int]:
    """从最新消息向前累加，返回预算内可原样保留的消息数和 token 估算。"""

    if token_budget <= 0:
        return 0, 0
    total_tokens = 0
    count = 0
    for _, token_count in reversed(message_token_pairs):
        next_total = total_tokens + token_count
        if count > 0 and next_total > token_budget:
            break
        if count == 0 and token_count > token_budget:
            return 1, token_count
        total_tokens = next_total
        count += 1
    return count, total_tokens


def _truncate_text(text: str, limit: int) -> str:
    """截断用于估算的工具结果，避免大型 JSON 影响策略稳定性。"""

    return text if len(text) <= limit else text[:limit]


def _stringify_for_estimation(value: Any) -> str:
    """把任意消息内容归一为可估算 token 的文本。"""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _positive_int(value: Any, fallback: int) -> int:
    """把用户配置归一化为正整数，非法值退回保守默认。"""

    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return fallback
    return normalized if normalized > 0 else fallback


def _bounded_float(value: Any, fallback: float, *, lower: float, upper: float) -> float:
    """把比例配置限制在允许范围内，非法值退回默认。"""

    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(upper, max(lower, normalized))
