"""文件功能：定义 Runtime 文件上传接口的请求与响应模型。"""

from pydantic import BaseModel, Field

from app.schemas.common import SchemaBase


class RuntimePageUploadItem(BaseModel):
    """单个页面文件上传项，由前端显式指定页面 ID 与目标文件名。"""

    page_id: int = Field(ge=1)
    file_name: str = Field(min_length=1, max_length=255)


class RuntimePageBatchUploadRequest(BaseModel):
    """批量上传页面源码到 Runtime 的请求。"""

    target_path: str = Field(min_length=1)
    files: list[RuntimePageUploadItem] = Field(min_length=1)


class RuntimeUploadedFileItem(SchemaBase):
    """单个 Runtime 上传结果。"""

    page_id: int
    code: str
    file_name: str
    path: str
    content_hash: str


class RuntimePageBatchUploadResponse(SchemaBase):
    """批量上传页面源码到 Runtime 的响应。"""

    message: str
    target_path: str
    files: list[RuntimeUploadedFileItem]


class RuntimePreviewLinkRequest(BaseModel):
    """生成 Runtime 页面预览链接的请求。"""

    file_path: str = Field(min_length=1)
    project_id: int = Field(ge=1)


class RuntimePreviewUploadRequest(BaseModel):
    """上传指定源码内容并立即生成预览链接的请求。"""

    target_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1, max_length=255)
    content: str
    project_id: int = Field(ge=1)


class RuntimePreviewLinkResponse(SchemaBase):
    """Runtime 页面预览链接响应。"""

    file_path: str
    preview_url: str
