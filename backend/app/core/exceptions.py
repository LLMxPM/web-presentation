"""文件功能：定义服务层统一业务异常，便于接口层输出一致错误语义。"""

from __future__ import annotations

from typing import Any


class AppException(Exception):
    """通用业务异常，包含 HTTP 状态码、业务码和面向前端的提示信息。"""

    def __init__(self, status_code: int, code: str, detail: str, data: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.data = data
        super().__init__(detail)
