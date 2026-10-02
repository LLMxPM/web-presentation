"""文件功能：定义系统设置与诊断管理接口的请求和响应模型。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import SchemaBase


class SystemSettingItem(SchemaBase):
    """单个系统设置项模型。"""

    key: str
    category: str
    description: str
    value: Any = None
    is_secret: bool = False
    is_env_overridden: bool = False
    source: str = "default"  # env / db / default
    updated_at: datetime | None = None
    updated_by: int | None = None


class SystemSettingCategoryGroup(SchemaBase):
    """按分类组织的系统设置组模型。"""

    category: str
    category_name: str
    items: list[SystemSettingItem]


class SystemSettingsListResponse(SchemaBase):
    """系统设置列表接口响应。"""

    items: list[SystemSettingItem]
    categories: list[SystemSettingCategoryGroup]
    safe_mode_warnings: list[dict[str, Any]] = Field(default_factory=list)


class SystemSettingsUpdateRequest(BaseModel):
    """批量更新系统设置的请求模型。"""

    settings: dict[str, Any] = Field(description="键值对字典，包含待更新的配置项")


class S3TestConnectionRequest(BaseModel):
    """S3 兼容对象存储连通性测试请求模型。"""

    endpoint_url: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    bucket: str = Field(min_length=1, description="主存储桶名称")
    region: str | None = None


class S3TestConnectionResponse(SchemaBase):
    """S3 连通性测试响应模型。"""

    success: bool
    message: str
