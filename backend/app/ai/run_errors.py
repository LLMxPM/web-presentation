"""文件功能：归一化智能体运行异常，避免把底层模型或网络错误直接暴露给用户。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STREAM_INTERRUPTED_MESSAGE = (
    "模型连接中断，本次输出没有完整返回。已保留当前对话进度，请重试；"
    "如果连续出现，请降低单次任务复杂度或调整模型输出上限。"
)
REQUEST_REJECTED_MESSAGE = "模型服务拒绝了本次请求，请检查当前模型名称、模型能力和高级参数配置。"
RATE_LIMITED_MESSAGE = "模型服务当前繁忙或触发限流，请稍后重试。"
PAYMENT_REQUIRED_MESSAGE = "模型服务余额或额度不足，请检查当前供应商账号的计费状态、余额或用量额度。"
TIMEOUT_MESSAGE = "模型服务响应超时，本次运行已停止。请稍后重试，或把任务拆成更小的步骤。"
GENERIC_RUN_FAILED_MESSAGE = "智能体运行中断，请稍后重试。若多次出现，请检查当前模型配置和网络连接。"


@dataclass(frozen=True)
class AgentRunFailure:
    """描述一次可展示给用户的智能体运行失败。"""

    code: str
    message: str
    raw_message: str


def build_agent_error_log_extra(
    error: BaseException,
    *,
    event: str,
    error_code: str,
    user_error_message: str | None = None,
    raw_error_message: str | None = None,
    **context: Any,
) -> dict[str, Any]:
    """构建智能体错误日志字段，保留原始异常链并附带业务定位上下文。"""

    return {
        "event": event,
        **context,
        "error_code": error_code,
        "user_error_message": user_error_message,
        "raw_error_type": type(error).__name__,
        "raw_error_module": type(error).__module__,
        "raw_error_message": raw_error_message if raw_error_message is not None else _raw_error_message(error),
        "raw_error_chain": _error_chain(error),
    }


def normalize_agent_run_exception(
    error: BaseException,
    *,
    fallback_code: str,
    fallback_message: str = GENERIC_RUN_FAILED_MESSAGE,
) -> AgentRunFailure:
    """把未知异常映射为稳定错误码和友好文案，保留原始信息供日志记录。"""

    raw_message = str(error).strip()
    normalized = raw_message.lower()
    if _contains_any(normalized, ("incomplete chunked read", "peer closed connection", "remote protocol error", "server disconnected")):
        return AgentRunFailure(
            code="AI_MODEL_STREAM_INTERRUPTED",
            message=STREAM_INTERRUPTED_MESSAGE,
            raw_message=raw_message,
        )
    if _contains_any(normalized, ("read timeout", "timed out", "timeout")):
        return AgentRunFailure(code="AI_MODEL_TIMEOUT", message=TIMEOUT_MESSAGE, raw_message=raw_message)
    if "status_code: 429" in normalized or "rate limit" in normalized:
        return AgentRunFailure(code="AI_MODEL_RATE_LIMITED", message=RATE_LIMITED_MESSAGE, raw_message=raw_message)
    if _contains_any(normalized, ("status_code: 402", "error code: 402", "payment required", "insufficient balance")):
        return AgentRunFailure(
            code="AI_MODEL_PAYMENT_REQUIRED",
            message=PAYMENT_REQUIRED_MESSAGE,
            raw_message=raw_message,
        )
    if "status_code: 400" in normalized or "invalid_request_error" in normalized:
        return AgentRunFailure(
            code="AI_MODEL_REQUEST_REJECTED",
            message=REQUEST_REJECTED_MESSAGE,
            raw_message=raw_message,
        )
    return AgentRunFailure(
        code=fallback_code,
        message=fallback_message,
        raw_message=raw_message,
    )


def _contains_any(value: str, patterns: tuple[str, ...]) -> bool:
    """判断字符串是否命中任一错误特征。"""

    return any(pattern in value for pattern in patterns)


def _raw_error_message(error: BaseException) -> str:
    """提取异常原始消息；空消息时使用异常类名兜底，便于日志检索。"""

    return str(error).strip() or type(error).__name__


def _error_chain(error: BaseException) -> list[dict[str, str]]:
    """展开异常 cause/context 链路，避免只看到最外层兜底异常。"""

    chain: list[dict[str, str]] = []
    visited: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in visited and len(chain) < 8:
        visited.add(id(current))
        chain.append(
            {
                "type": type(current).__name__,
                "module": type(current).__module__,
                "message": _raw_error_message(current),
            }
        )
        if current.__cause__ is not None:
            current = current.__cause__
            continue
        if current.__suppress_context__:
            break
        current = current.__context__
    return chain
