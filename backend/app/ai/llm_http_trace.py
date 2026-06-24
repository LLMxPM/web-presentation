"""文件功能：为开发环境记录智能体调用大模型供应商时的 HTTP 请求与响应摘要。"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from pydantic_ai.models import get_user_agent

from app.core.config import get_settings
from app.models.ai_llm import AiLlmConfig

logger = logging.getLogger(__name__)

_TRACE_ID_EXTENSION = "llm_http_trace_id"
_TRACE_STARTED_AT_EXTENSION = "llm_http_trace_started_at"
_WRITE_LOCK = threading.Lock()

_SENSITIVE_HEADER_KEYS = {
    "authorization",
    "api-key",
    "x-api-key",
    "anthropic-api-key",
    "cookie",
    "set-cookie",
}
_SENSITIVE_PAYLOAD_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "access_key",
    "credential",
}
_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "access_key",
    "awsaccesskeyid",
    "signature",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-security-token",
}
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.=-]{16,}")
_JWT_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b")
_FIELD_SECRET_PATTERN = re.compile(
    r"(?i)([\"']?(?:api_key|apikey|authorization|token|access_token|refresh_token|secret|password|access_key|credential)"
    r"[\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^,&\s}]+)"
)


def build_llm_http_trace_client(config: AiLlmConfig) -> httpx.AsyncClient | None:
    """按当前配置返回可注入 Pydantic AI provider 的 trace HTTP client；默认关闭。"""

    settings = get_settings()
    if not settings.ai_llm_http_trace_enabled:
        return None

    trace_dir = str(settings.ai_llm_http_trace_dir_path)
    client = _cached_trace_client(
        trace_dir=trace_dir,
        body_max_bytes=settings.ai_llm_http_trace_body_max_bytes,
        config_id=config.id,
        provider_key=str(config.provider_key or ""),
        model_id=str(config.model_id or ""),
    )
    if client.is_closed:
        _cached_trace_client.cache_clear()
        client = _cached_trace_client(
            trace_dir=trace_dir,
            body_max_bytes=settings.ai_llm_http_trace_body_max_bytes,
            config_id=config.id,
            provider_key=str(config.provider_key or ""),
            model_id=str(config.model_id or ""),
        )
    return client


def build_llm_http_trace_hooks(
    *,
    trace_dir: Path,
    body_max_bytes: int,
    metadata: dict[str, Any],
) -> dict[str, list[Any]]:
    """构造 httpx event hooks，便于业务注入与单元测试复用同一套记录逻辑。"""

    async def on_request(request: httpx.Request) -> None:
        """记录发往供应商的请求头和请求体；读取请求体后交还给 httpx 继续发送。"""

        trace_id = uuid4().hex
        request.extensions[_TRACE_ID_EXTENSION] = trace_id
        request.extensions[_TRACE_STARTED_AT_EXTENSION] = monotonic()
        try:
            body = await request.aread()
            _write_trace_record(
                trace_dir,
                {
                    **_base_record("llm.http.request", trace_id=trace_id, metadata=metadata),
                    "method": request.method,
                    "url": _redact_url(str(request.url)),
                    "headers": _redact_headers(request.headers),
                    "body": _format_body(body, max_bytes=body_max_bytes),
                },
            )
        except Exception:
            logger.warning(
                "记录 LLM HTTP 请求 trace 失败。",
                exc_info=True,
                extra={"event": "llm.http_trace.request_failed"},
            )

    async def on_response(response: httpx.Response) -> None:
        """记录供应商响应状态和响应头，不读取 body，避免影响流式响应消费。"""

        trace_id = str(response.request.extensions.get(_TRACE_ID_EXTENSION) or uuid4().hex)
        started_at = response.request.extensions.get(_TRACE_STARTED_AT_EXTENSION)
        duration_ms = None
        if isinstance(started_at, (int, float)):
            duration_ms = round((monotonic() - started_at) * 1000, 2)
        try:
            _write_trace_record(
                trace_dir,
                {
                    **_base_record("llm.http.response", trace_id=trace_id, metadata=metadata),
                    "method": response.request.method,
                    "url": _redact_url(str(response.request.url)),
                    "status_code": response.status_code,
                    "reason_phrase": response.reason_phrase,
                    "http_version": response.http_version,
                    "duration_ms": duration_ms,
                    "headers": _redact_headers(response.headers),
                },
            )
        except Exception:
            logger.warning(
                "记录 LLM HTTP 响应 trace 失败。",
                exc_info=True,
                extra={"event": "llm.http_trace.response_failed"},
            )

    return {"request": [on_request], "response": [on_response]}


def clear_llm_http_trace_client_cache() -> None:
    """清理 trace client 缓存；主要供测试或开发期热切换配置使用。"""

    _cached_trace_client.cache_clear()


@lru_cache(maxsize=64)
def _cached_trace_client(
    *,
    trace_dir: str,
    body_max_bytes: int,
    config_id: int | None,
    provider_key: str,
    model_id: str,
) -> httpx.AsyncClient:
    """按模型配置缓存 trace client，避免每次 run 新建未关闭的连接池。"""

    metadata = {
        "llm_config_id": config_id,
        "provider_key": provider_key,
        "model_id": model_id,
    }
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=600, connect=5),
        headers={"User-Agent": get_user_agent()},
        event_hooks=build_llm_http_trace_hooks(
            trace_dir=Path(trace_dir),
            body_max_bytes=body_max_bytes,
            metadata=metadata,
        ),
    )


def _base_record(event: str, *, trace_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """生成 trace 记录公共字段，确保 JSONL 字段稳定。"""

    return {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        "trace_id": trace_id,
        **metadata,
    }


def _write_trace_record(trace_dir: Path, record: dict[str, Any]) -> None:
    """把单条 trace 记录追加到当天 JSONL 文件，写入失败交由调用方处理。"""

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    with _WRITE_LOCK:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / f"llm-http-{day}.jsonl"
        with trace_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str))
            file.write("\n")


def _format_body(body: bytes, *, max_bytes: int) -> dict[str, Any]:
    """把请求体转换为可读、脱敏且有大小上限的 trace 字段。"""

    size_bytes = len(body)
    if size_bytes == 0:
        return {
            "size_bytes": 0,
            "truncated": False,
            "encoding": "utf-8",
            "content": "",
        }

    truncated = size_bytes > max_bytes
    content_bytes = body[:max_bytes]
    content = content_bytes.decode("utf-8", errors="replace")
    body_format = "text"
    if not truncated and content.lstrip().startswith(("{", "[")):
        try:
            redacted = _redact_sensitive_payload(json.loads(content))
            content = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
            body_format = "json"
        except json.JSONDecodeError:
            content = _redact_trace_text(content)
    else:
        content = _redact_trace_text(content)

    if len(content.encode("utf-8")) > max_bytes:
        content = _truncate_text_by_bytes(content, max_bytes=max_bytes)
        truncated = True

    return {
        "size_bytes": size_bytes,
        "truncated": truncated,
        "encoding": "utf-8",
        "format": body_format,
        "content": content,
    }


def _redact_headers(headers: httpx.Headers) -> dict[str, str]:
    """脱敏 HTTP headers，保留排障常用的非敏感字段。"""

    redacted: dict[str, str] = {}
    for key, value in headers.multi_items():
        normalized = key.lower()
        if normalized in _SENSITIVE_HEADER_KEYS:
            redacted[key] = "[redacted]"
        else:
            redacted[key] = _redact_trace_text(value)
    return redacted


def _redact_url(raw_url: str) -> str:
    """脱敏 URL 查询参数中的凭据，避免预签名 URL 或 token 落盘。"""

    try:
        parts = urlsplit(raw_url)
        query = urlencode(
            [
                (key, "[redacted]" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
            ],
            doseq=True,
            safe="[]",
        )
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:
        return _redact_trace_text(raw_url)


def _redact_sensitive_payload(value: Any) -> Any:
    """递归脱敏 JSON 请求体中的密钥字段，同时保留 prompt/content 等排障字段。"""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = _normalize_key(str(key))
            if _is_sensitive_payload_key(normalized_key):
                result[str(key)] = "[redacted]"
            else:
                result[str(key)] = _redact_sensitive_payload(item)
        return result
    if isinstance(value, list):
        return [_redact_sensitive_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_trace_text(value)
    return value


def _is_sensitive_payload_key(normalized_key: str) -> bool:
    """判断 JSON 字段名是否代表凭据；避免误伤 max_tokens 等模型参数。"""

    if normalized_key in _SENSITIVE_PAYLOAD_KEYS:
        return True
    return normalized_key.endswith(("_api_key", "_token", "_secret", "_password", "_access_key", "_credential"))


def _normalize_key(key: str) -> str:
    """统一字段名比较格式，兼容横线、空格和大小写差异。"""

    return key.strip().lower().replace("-", "_").replace(" ", "_")


def _redact_trace_text(value: str) -> str:
    """脱敏文本中的常见凭据形态，保留其它原文用于开发排障。"""

    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", value)
    redacted = _JWT_PATTERN.sub("[redacted-token]", redacted)
    redacted = _FIELD_SECRET_PATTERN.sub(r"\1[redacted]", redacted)
    return redacted


def _truncate_text_by_bytes(value: str, *, max_bytes: int) -> str:
    """按 UTF-8 字节数截断文本，避免半个中文字符导致解码异常。"""

    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return f"{encoded[:max_bytes].decode('utf-8', errors='ignore')}...[truncated]"
