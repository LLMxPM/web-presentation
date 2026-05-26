"""文件功能：配置 Backend 结构化日志、请求 ID 上下文和日志脱敏工具。"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

from app.core.config import AppSettings


SERVICE_NAME = "backend"
DEFAULT_EVENT = "log"
MAX_LOG_STRING_LENGTH = 4096
MAX_LOG_DEPTH = 5

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_MANAGED_HANDLER_ATTR = "_web_presentation_managed_handler"
_LOG_RECORD_RESERVED = set(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
)
_LOG_RECORD_IGNORED_FIELDS = {"color_message"}
_SENSITIVE_KEYWORDS = {
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "ctx",
    "secret",
    "password",
    "api_key",
    "apikey",
    "access_key",
    "refresh_token",
    "database_url",
}
_CONTENT_KEYWORDS = {
    "body",
    "content",
    "page_content",
    "source_code",
    "prompt",
    "result",
    "response",
}
_JWT_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.=-]{16,}")
_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:token|ctx|authorization|api_key|apikey|secret|password|access_key)=)[^&\s]+"
)
_DATABASE_PASSWORD_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@\s/]+(@)")


def configure_app_logging(settings: AppSettings) -> None:
    """按环境配置 Backend 进程日志，输出到标准输出并降低第三方访问日志噪声。"""

    log_level = _coerce_log_level(settings.log_level)
    formatter: logging.Formatter
    if settings.log_format.lower() == "json":
        formatter = JsonLineFormatter(service=SERVICE_NAME)
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s"
        )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    for handler in list(root_logger.handlers):
        if getattr(handler, _MANAGED_HANDLER_ATTR, False):
            root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    setattr(stream_handler, _MANAGED_HANDLER_ATTR, True)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)
    root_logger.addHandler(stream_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.asgi"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(log_level)
        uvicorn_logger.propagate = True
        for handler in list(uvicorn_logger.handlers):
            uvicorn_logger.removeHandler(handler)
    third_party_level = logging.INFO if log_level <= logging.DEBUG else logging.WARNING
    for logger_name in ("sqlalchemy", "alembic"):
        logging.getLogger(logger_name).setLevel(third_party_level)
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.setLevel(logging.WARNING)
    uvicorn_access_logger.propagate = False
    for handler in list(uvicorn_access_logger.handlers):
        uvicorn_access_logger.removeHandler(handler)


def bind_request_id(request_id: str) -> contextvars.Token[str]:
    """把当前请求 ID 写入上下文，供同一协程链路中的日志自动携带。"""

    return _request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token[str]) -> None:
    """恢复请求 ID 上下文，避免异步请求之间互相污染。"""

    _request_id_var.reset(token)


def get_current_request_id() -> str:
    """读取当前请求 ID；后台任务无请求上下文时返回空字符串。"""

    return _request_id_var.get()


def sanitize_log_value(
    value: Any,
    *,
    max_string_length: int = MAX_LOG_STRING_LENGTH,
    max_depth: int = MAX_LOG_DEPTH,
) -> Any:
    """递归脱敏并裁剪日志字段，避免凭据、源码正文或大段 payload 进入日志。"""

    return _sanitize_log_value(value, max_string_length=max_string_length, max_depth=max_depth, depth=0)


def sanitize_log_text(value: str, *, max_length: int = MAX_LOG_STRING_LENGTH) -> str:
    """脱敏单个字符串字段，并按最大长度截断。"""

    redacted = _DATABASE_PASSWORD_PATTERN.sub(r"\1[redacted]\2", str(value))
    redacted = _QUERY_SECRET_PATTERN.sub(r"\1[redacted]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _JWT_PATTERN.sub("[redacted-token]", redacted)
    if len(redacted) <= max_length:
        return redacted
    return f"{redacted[: max(0, max_length - 15)]}...[truncated]"


class JsonLineFormatter(logging.Formatter):
    """把 Python LogRecord 格式化为单行 JSON，字段稳定且自动脱敏。"""

    def __init__(self, *, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        """输出符合平台日志契约的 JSON Lines 文本。"""

        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": getattr(record, "service", self.service),
            "module": getattr(record, "log_module", record.name),
            "event": getattr(record, "event", DEFAULT_EVENT),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_current_request_id(),
        }

        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_RESERVED or key in _LOG_RECORD_IGNORED_FIELDS or key in payload or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["error"] = _format_exception(record.exc_info)

        sanitized = sanitize_log_value(payload)
        return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"), default=str)


def _sanitize_log_value(
    value: Any,
    *,
    max_string_length: int,
    max_depth: int,
    depth: int,
) -> Any:
    """递归执行实际脱敏；通过 depth 控制复杂对象展开层级。"""

    if depth > max_depth:
        return "[max-depth]"
    if isinstance(value, str):
        return sanitize_log_text(value, max_length=max_string_length)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            lowered_key = normalized_key.lower()
            if any(keyword in lowered_key for keyword in _SENSITIVE_KEYWORDS):
                result[normalized_key] = "[redacted]"
                continue
            if any(keyword == lowered_key or lowered_key.endswith(f"_{keyword}") for keyword in _CONTENT_KEYWORDS):
                result[normalized_key] = "[omitted]"
                continue
            result[normalized_key] = _sanitize_log_value(
                item,
                max_string_length=max_string_length,
                max_depth=max_depth,
                depth=depth + 1,
            )
        return result
    if isinstance(value, (list, tuple, set)):
        return [
            _sanitize_log_value(
                item,
                max_string_length=max_string_length,
                max_depth=max_depth,
                depth=depth + 1,
            )
            for item in list(value)[:50]
        ]
    return sanitize_log_text(str(value), max_length=max_string_length)


def _format_exception(exc_info: tuple[type[BaseException], BaseException, Any]) -> dict[str, str]:
    """把异常信息转换为结构化对象，并控制栈长度。"""

    error_type, error, _ = exc_info
    stack = "".join(traceback.format_exception(*exc_info))
    return {
        "type": error_type.__name__,
        "message": sanitize_log_text(str(error), max_length=1024),
        "stack": sanitize_log_text(stack, max_length=MAX_LOG_STRING_LENGTH),
    }


def _coerce_log_level(raw_level: str) -> int:
    """把环境变量中的日志等级转为 logging 模块常量，非法值回退到 INFO。"""

    normalized = str(raw_level or "INFO").strip().upper()
    return int(getattr(logging, normalized, logging.INFO))
