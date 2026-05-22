"""文件功能：定义平台用户管理接口的请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import RecordStatus, UserRole
from app.schemas.common import SchemaBase


class UserItem(SchemaBase):
    """平台用户列表与详情响应。"""

    id: int
    username: str
    display_name: str
    role: UserRole
    status: RecordStatus
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreateRequest(BaseModel):
    """平台管理员创建用户的请求。"""

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    role: UserRole = UserRole.WORKSPACE_USER
    status: RecordStatus = RecordStatus.ACTIVE


class UserUpdateRequest(BaseModel):
    """平台管理员更新用户资料、角色或状态的请求。"""

    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    role: UserRole | None = None
    status: RecordStatus | None = None


class UserResetPasswordRequest(BaseModel):
    """平台管理员重置用户密码的请求。"""

    new_password: str = Field(min_length=8, max_length=128)
