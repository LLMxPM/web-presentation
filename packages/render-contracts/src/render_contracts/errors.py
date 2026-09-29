"""文件功能：定义远程渲染统一错误模型、错误码、分类与 HTTP 状态映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

ERROR_CODE_QUEUE_FULL: Final[str] = "RENDER_QUEUE_FULL"
ERROR_CODE_WORKER_BUSY: Final[str] = "RENDER_WORKER_BUSY"
ERROR_CODE_SERVICE_UNAVAILABLE: Final[str] = "RENDER_SERVICE_UNAVAILABLE"
ERROR_CODE_CONTRACT_MISMATCH: Final[str] = "RENDER_CONTRACT_MISMATCH"
ERROR_CODE_PROFILE_MISMATCH: Final[str] = "RENDER_PROFILE_MISMATCH"
ERROR_CODE_INPUT_EXPIRED: Final[str] = "RENDER_INPUT_EXPIRED"
ERROR_CODE_INPUT_NOT_REPRODUCIBLE: Final[str] = "RENDER_INPUT_NOT_REPRODUCIBLE"
ERROR_CODE_CONTENT_ERROR: Final[str] = "RENDER_CONTENT_ERROR"
ERROR_CODE_ASSET_NOT_READY: Final[str] = "RENDER_ASSET_NOT_READY"
ERROR_CODE_BROWSER_LOST: Final[str] = "RENDER_BROWSER_LOST"
ERROR_CODE_DEADLINE_EXCEEDED: Final[str] = "RENDER_DEADLINE_EXCEEDED"
ERROR_CODE_RESULT_LOST: Final[str] = "RENDER_RESULT_LOST"
ERROR_CODE_OUTPUT_LIMIT_EXCEEDED: Final[str] = "RENDER_OUTPUT_LIMIT_EXCEEDED"
ERROR_CODE_CANCELLED: Final[str] = "RENDER_CANCELLED"
ERROR_CODE_INTERNAL_ERROR: Final[str] = "RENDER_INTERNAL_ERROR"

CATEGORY_CAPACITY: Final[str] = "capacity"
CATEGORY_INFRASTRUCTURE: Final[str] = "infrastructure"
CATEGORY_CONFIGURATION: Final[str] = "configuration"
CATEGORY_INPUT: Final[str] = "input"
CATEGORY_CONTENT: Final[str] = "content"
CATEGORY_RESOURCE: Final[str] = "resource"
CATEGORY_TIMEOUT: Final[str] = "timeout"
CATEGORY_CANCELLATION: Final[str] = "cancellation"
CATEGORY_INTERNAL: Final[str] = "internal"

# (category, retryable, http_status)：HTTP 状态是 Backend 业务 API 的单源映射，
# Backend 不得在别处再维护第二份错误码→状态码表。
_ERROR_META: Final[dict[str, tuple[str, bool, int]]] = {
    ERROR_CODE_QUEUE_FULL: (CATEGORY_CAPACITY, False, 429),
    ERROR_CODE_WORKER_BUSY: (CATEGORY_CAPACITY, True, 503),
    ERROR_CODE_SERVICE_UNAVAILABLE: (CATEGORY_INFRASTRUCTURE, True, 503),
    ERROR_CODE_CONTRACT_MISMATCH: (CATEGORY_CONFIGURATION, False, 500),
    ERROR_CODE_PROFILE_MISMATCH: (CATEGORY_CONFIGURATION, False, 500),
    ERROR_CODE_INPUT_EXPIRED: (CATEGORY_INPUT, False, 409),
    ERROR_CODE_INPUT_NOT_REPRODUCIBLE: (CATEGORY_INPUT, False, 422),
    ERROR_CODE_CONTENT_ERROR: (CATEGORY_CONTENT, False, 422),
    ERROR_CODE_ASSET_NOT_READY: (CATEGORY_RESOURCE, True, 409),
    ERROR_CODE_BROWSER_LOST: (CATEGORY_INFRASTRUCTURE, True, 500),
    # attempt 级超时可在剩余次数内重试；请求总预算耗尽由仓储收敛为 expired。
    ERROR_CODE_DEADLINE_EXCEEDED: (CATEGORY_TIMEOUT, True, 504),
    ERROR_CODE_RESULT_LOST: (CATEGORY_INFRASTRUCTURE, True, 502),
    ERROR_CODE_OUTPUT_LIMIT_EXCEEDED: (CATEGORY_RESOURCE, False, 422),
    ERROR_CODE_CANCELLED: (CATEGORY_CANCELLATION, False, 409),
    ERROR_CODE_INTERNAL_ERROR: (CATEGORY_INTERNAL, True, 500),
}

DEFAULT_ERROR_HTTP_STATUS: Final[int] = 500


@dataclass(slots=True, frozen=True)
class RenderError:
    """统一渲染错误结构，message 为可展示的脱敏摘要。"""

    code: str
    category: str
    stage: str
    retryable: bool
    message: str
    trace_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """序列化为调用方可读的错误字典。"""

        return {
            "code": self.code,
            "category": self.category,
            "stage": self.stage,
            "retryable": self.retryable,
            "message": self.message,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_code(
        cls,
        code: str,
        *,
        message: str,
        stage: str = "execution",
        retryable: bool | None = None,
        trace_id: str | None = None,
    ) -> "RenderError":
        """按错误码推断类别与默认可重试性。"""

        category, default_retryable, _http_status = _ERROR_META.get(
            code, (CATEGORY_INTERNAL, True, DEFAULT_ERROR_HTTP_STATUS)
        )
        return cls(
            code=code,
            category=category,
            stage=stage,
            retryable=default_retryable if retryable is None else retryable,
            message=message,
            trace_id=trace_id,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RenderError":
        """从字典反序列化错误结构。"""

        code = str(payload.get("code") or ERROR_CODE_INTERNAL_ERROR)
        meta = _ERROR_META.get(code, (CATEGORY_INTERNAL, True, DEFAULT_ERROR_HTTP_STATUS))
        default_retryable = meta[1]
        category = str(payload.get("category") or meta[0])
        stage = str(payload.get("stage") or "execution")
        retryable = parse_bool(payload.get("retryable", default_retryable), default=default_retryable)
        message = str(payload.get("message") or "渲染执行失败。")
        raw_trace = payload.get("trace_id")
        trace_id = str(raw_trace) if raw_trace else None
        return cls(
            code=code,
            category=category,
            stage=stage,
            retryable=retryable,
            message=message,
            trace_id=trace_id,
        )


def http_status_for_error_code(code: str) -> int:
    """按错误码返回业务 API 应使用的 HTTP 状态；未知码归为 500。"""

    return _ERROR_META.get(code, (CATEGORY_INTERNAL, True, DEFAULT_ERROR_HTTP_STATUS))[2]


def error_http_status_table() -> dict[str, int]:
    """导出完整错误码→HTTP 状态表，供契约对拍与文档生成。"""

    return {code: meta[2] for code, meta in _ERROR_META.items()}


class RenderContractError(ValueError):
    """契约层校验失败，不代表执行基础设施故障。"""

    def __init__(self, message: str, *, code: str = ERROR_CODE_CONTRACT_MISMATCH) -> None:
        super().__init__(message)
        self.code = code


def parse_bool(value: object, *, default: bool = False) -> bool:
    """显式解析布尔字段，避免字符串 'false' 被 bool() 误判为真。"""

    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        return default
    return bool(value)


class RenderExecutionError(RuntimeError):
    """渲染执行链路错误，携带统一错误结构。"""

    def __init__(self, error: RenderError) -> None:
        super().__init__(error.message)
        self.error = error
