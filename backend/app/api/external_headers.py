"""文件功能：统一外部 API 幂等键 Header 的公开 Schema 与运行校验，保持业务 400 错误语义。"""

from typing import Annotated

from fastapi import Header

from app.core.exceptions import AppException

MAX_KEY_LENGTH = 128
IdempotencyKeyHeader = Annotated[str | None, Header(
    alias="Idempotency-Key",
    json_schema_extra={"minLength": 1, "maxLength": MAX_KEY_LENGTH, "pattern": "^[!-~]+$"},
)]


def require_idempotency_key(value: str | None, operation: str) -> None:
    """写入前要求原键为 1～128 字符的可打印 ASCII；非法值不归一化或裁剪。"""
    if not value or not value.strip():
        raise AppException(400, "IDEMPOTENCY_KEY_REQUIRED", f"操作 '{operation}' 必须携带非空的 Idempotency-Key。")
    if len(value) > MAX_KEY_LENGTH or any(not 33 <= ord(char) <= 126 for char in value):
        raise AppException(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 必须为不含空白且不超过 128 字符的 ASCII 标识。")
