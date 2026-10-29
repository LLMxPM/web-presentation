"""文件功能：校验独立静态呈现回执，区分内容不可呈现、准备失败与协议缺失。"""

from typing import Any

from render_contracts.errors import (
    ERROR_CODE_ASSET_NOT_READY,
    ERROR_CODE_CONTRACT_MISMATCH,
    ERROR_CODE_STATIC_PRESENTATION_UNAVAILABLE,
    RenderError,
    RenderExecutionError,
)


def require_static_presentation(bridge: dict[str, Any]) -> None:
    """仅 ready 允许捕获；不可呈现不可重试，不通过推进动画或猜测画面兜底。"""
    receipt = bridge.get("staticPresentation")
    if not isinstance(receipt, dict) or receipt.get("status") not in {"ready", "unsupported", "failed"}:
        raise RenderExecutionError(RenderError.from_code(
            ERROR_CODE_CONTRACT_MISMATCH, message="Runtime 缺少独立静态呈现回执。", stage="ready",
        ))
    if receipt["status"] == "ready":
        return
    unavailable = receipt["status"] == "unsupported"
    raise RenderExecutionError(RenderError.from_code(
        ERROR_CODE_STATIC_PRESENTATION_UNAVAILABLE if unavailable else ERROR_CODE_ASSET_NOT_READY,
        message=str(receipt.get("message") or "页面未提供可用的静态呈现。")[:240],
        stage="ready", retryable=False if unavailable else None,
    ))
