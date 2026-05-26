"""文件功能：验证 Backend 结构化日志格式、请求 ID 上下文和脱敏规则。"""

from __future__ import annotations

import json
import logging

from app.api.routes.client_logs import _build_safe_client_error_payload
from app.core.logging_config import JsonLineFormatter, bind_request_id, reset_request_id, sanitize_log_text
from app.schemas.client_log import ClientErrorLogRequest


def test_json_formatter_should_emit_contract_fields_and_request_id() -> None:
    """JSON formatter 应输出固定字段，并自动读取 request_id 上下文。"""

    token = bind_request_id("req-test")
    try:
        record = logging.LogRecord("app.demo", logging.INFO, __file__, 10, "hello %s", ("world",), None)
        record.event = "demo.event"  # type: ignore[attr-defined]
        line = JsonLineFormatter(service="backend").format(record)
    finally:
        reset_request_id(token)

    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["service"] == "backend"
    assert payload["module"] == "app.demo"
    assert payload["event"] == "demo.event"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-test"


def test_sanitize_log_text_should_redact_tokens_and_database_password() -> None:
    """脱敏工具不能把 token、Bearer 和数据库密码写入日志。"""

    raw = (
        "postgresql+asyncpg://user:secret@db:5432/app?"
        "token=aaa.bbbbbbbbbbbb.cccccccccccc Authorization=Bearer abcdefghijklmnopqrstuvwxyz"
    )

    sanitized = sanitize_log_text(raw)

    assert "secret" not in sanitized
    assert "aaa.bbbbbbbbbbbb.cccccccccccc" not in sanitized
    assert "abcdefghijklmnopqrstuvwxyz" not in sanitized
    assert "[redacted]" in sanitized or "[redacted-token]" in sanitized


def test_client_error_payload_should_truncate_large_stack_and_redact_context() -> None:
    """客户端错误日志应按大小上限裁剪，并对上下文敏感字段脱敏。"""

    payload = ClientErrorLogRequest(
        source="editor",
        message="浏览器错误",
        stack="x" * 8000,
        context={
            "token": "should-hide",
            "page_content": "<template>large source</template>",
            "safe": "ok",
        },
    )

    safe_payload = _build_safe_client_error_payload(payload, user_id=7, max_bytes=800)

    assert safe_payload["user_id"] == 7
    assert safe_payload["stack"] == "[truncated]"
    assert safe_payload["context"] == {"truncated": True}
    assert "should-hide" not in json.dumps(safe_payload, ensure_ascii=False)
