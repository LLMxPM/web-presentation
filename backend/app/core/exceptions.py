"""文件功能：定义服务层统一业务异常，便于接口层输出一致错误语义。"""


class AppException(Exception):
    """通用业务异常，包含 HTTP 状态码、业务码和面向前端的提示信息。"""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)
