"""文件功能：冻结页面 Mutation 截图描述的公开字段，并保留既有页面/组件结果的增量兼容。"""

from typing import Any, Literal
from typing_extensions import TypedDict, NotRequired
from pydantic import ConfigDict


class MutationScreenshotResult(TypedDict):
    """ready 表示可读取的正式图片；pending 不暗示已入队，skipped 表示未请求截图。"""

    status: Literal["ready", "pending", "skipped"]
    version_no: int
    screenshot_id: NotRequired[str]
    width: NotRequired[int]
    height: NotRequired[int]
    reason_code: NotRequired[str | None]


class ExternalMutationResult(TypedDict, total=False):
    """只约束新增截图对象，其余已有及未来业务字段保持透传，不丢失旧客户端数据。"""

    __pydantic_config__ = ConfigDict(extra="allow")
    screenshot: MutationScreenshotResult
