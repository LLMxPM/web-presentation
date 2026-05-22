"""文件功能：定义通用分页、枚举和标准响应模型。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RecordStatus

T = TypeVar("T")


class SchemaBase(BaseModel):
    """所有响应模型的基础配置，允许直接从 ORM 对象解析。"""

    model_config = ConfigDict(from_attributes=True)


class PagedResponse(SchemaBase, Generic[T]):
    """分页查询标准响应，统一返回列表数据与总数。"""

    items: list[T]
    total: int
    page: int
    page_size: int


class MessageResponse(SchemaBase):
    """简单操作响应，用于删除、登出等无需复杂数据的场景。"""

    message: str


class ListQuery(SchemaBase):
    """列表请求查询参数，统一约束分页、筛选与排序能力。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    keyword: str | None = None
    status: RecordStatus | None = None
    sort_by: str = "updated_at"
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
