"""文件功能：把统一渲染错误映射为 Backend AppException，不保留旧 PLAYWRIGHT_* 码。"""

from __future__ import annotations

from render_contracts.errors import (
    ERROR_CODE_ASSET_NOT_READY,
    ERROR_CODE_CANCELLED,
    ERROR_CODE_CONTENT_ERROR,
    ERROR_CODE_CONTRACT_MISMATCH,
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_INPUT_EXPIRED,
    ERROR_CODE_INPUT_NOT_REPRODUCIBLE,
    ERROR_CODE_OUTPUT_LIMIT_EXCEEDED,
    ERROR_CODE_PROFILE_MISMATCH,
    ERROR_CODE_QUEUE_FULL,
    ERROR_CODE_RESULT_LOST,
    ERROR_CODE_SERVICE_UNAVAILABLE,
    ERROR_CODE_WORKER_BUSY,
    RenderError,
)

from app.core.exceptions import AppException

_STATUS_BY_CODE: dict[str, int] = {
    ERROR_CODE_QUEUE_FULL: 429,
    ERROR_CODE_WORKER_BUSY: 503,
    ERROR_CODE_SERVICE_UNAVAILABLE: 503,
    ERROR_CODE_CONTRACT_MISMATCH: 500,
    ERROR_CODE_PROFILE_MISMATCH: 500,
    ERROR_CODE_INPUT_EXPIRED: 409,
    ERROR_CODE_INPUT_NOT_REPRODUCIBLE: 422,
    ERROR_CODE_CONTENT_ERROR: 422,
    ERROR_CODE_ASSET_NOT_READY: 409,
    ERROR_CODE_DEADLINE_EXCEEDED: 504,
    ERROR_CODE_RESULT_LOST: 502,
    ERROR_CODE_OUTPUT_LIMIT_EXCEEDED: 422,
    ERROR_CODE_CANCELLED: 409,
}


def render_error_to_app_exception(error: RenderError) -> AppException:
    """把渲染错误转换为业务 API 可返回的 AppException。"""

    status = _STATUS_BY_CODE.get(error.code, 500)
    detail = error.message
    if error.trace_id:
        detail = f"{detail}（trace_id={error.trace_id}）"
    return AppException(status_code=status, code=error.code, detail=detail)


def render_error_from_exception(error: Exception, *, stage: str = "execution") -> RenderError:
    """把任意异常转换为统一渲染错误结构。"""

    if isinstance(error, AppException):
        return RenderError.from_code(
            error.code if error.code.startswith("RENDER_") else "RENDER_INTERNAL_ERROR",
            message=error.detail or str(error),
            stage=stage,
        )
    from render_contracts.errors import ERROR_CODE_BROWSER_LOST, ERROR_CODE_INTERNAL_ERROR

    text = str(error) or "渲染执行失败。"
    lowered = text.lower()
    if any(token in lowered for token in ("browser", "chromium", "target closed", "断连", "browser has been closed")):
        return RenderError.from_code(ERROR_CODE_BROWSER_LOST, message=text, stage=stage)
    return RenderError.from_code(ERROR_CODE_INTERNAL_ERROR, message=text, stage=stage)
