"""文件功能：定义浏览器端错误日志上报请求模型。"""

from typing import Literal

from pydantic import Field

from app.schemas.common import SchemaBase


class ClientErrorLogRequest(SchemaBase):
    """浏览器端错误日志上报载荷，只允许错误排障所需的有限字段。"""

    source: Literal["editor", "runtime-browser"]
    message: str = Field(min_length=1, max_length=4096)
    error_name: str | None = Field(default=None, max_length=256)
    stack: str | None = Field(default=None, max_length=8192)
    route: str | None = Field(default=None, max_length=1024)
    url: str | None = Field(default=None, max_length=2048)
    component: str | None = Field(default=None, max_length=512)
    trace_id: str | None = Field(default=None, max_length=256)
    artifact_id: str | None = Field(default=None, max_length=256)
    context: dict[str, object] = Field(default_factory=dict)
