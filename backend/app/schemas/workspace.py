"""文件功能：定义工作空间的创建、更新、列表与详情响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import RecordStatus
from app.schemas.common import SchemaBase


class WorkspaceCreateRequest(BaseModel):
    """创建工作空间入参，code 由后端自动生成。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus = RecordStatus.ACTIVE
    default_theme_key: str | None = Field(default=None, min_length=1, max_length=64)


class WorkspaceUpdateRequest(BaseModel):
    """更新工作空间入参，允许局部更新核心元数据（code 不可修改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus | None = None
    default_theme_key: str | None = Field(default=None, min_length=1, max_length=64)


class WorkspaceItem(SchemaBase):
    """工作空间响应模型，包含常用列表字段。"""

    id: int
    code: str
    name: str
    description: str | None
    status: RecordStatus
    last_opened_at: datetime | None
    default_theme_key: str | None
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None
