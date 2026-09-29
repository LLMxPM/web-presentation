"""文件功能：把统一渲染错误映射为 Backend AppException；HTTP 状态以 render_contracts 为单一事实源。"""

from __future__ import annotations

from render_contracts.errors import (
    ERROR_CODE_BROWSER_LOST,
    ERROR_CODE_INTERNAL_ERROR,
    RenderError,
    http_status_for_error_code,
)

from app.core.exceptions import AppException


def render_error_to_app_exception(error: RenderError) -> AppException:
    """把渲染错误转换为业务 API 可返回的 AppException。"""

    status = http_status_for_error_code(error.code)
    detail = error.message
    if error.trace_id:
        detail = f"{detail}（trace_id={error.trace_id}）"
    return AppException(status_code=status, code=error.code, detail=detail)


def render_error_from_exception(error: Exception, *, stage: str = "execution") -> RenderError:
    """把任意异常转换为统一渲染错误结构。"""

    if isinstance(error, AppException):
        return RenderError.from_code(
            error.code if error.code.startswith("RENDER_") else ERROR_CODE_INTERNAL_ERROR,
            message=error.detail or str(error),
            stage=stage,
        )

    text = str(error) or "渲染执行失败。"
    lowered = text.lower()
    if any(token in lowered for token in ("browser", "chromium", "target closed", "断连", "browser has been closed")):
        return RenderError.from_code(ERROR_CODE_BROWSER_LOST, message=text, stage=stage)
    return RenderError.from_code(ERROR_CODE_INTERNAL_ERROR, message=text, stage=stage)
