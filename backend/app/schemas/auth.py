"""文件功能：定义登录、鉴权和账号维护相关的请求与响应模型。"""

from datetime import datetime

from pydantic_core import PydanticCustomError
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.models.enums import RecordStatus, UserRole
from app.schemas.common import SchemaBase
from app.schemas.preview_size_preset import PreviewSizePreset


class LoginRequest(BaseModel):
    """用户登录入参，包含用户名和密码。"""

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    """修改密码入参，要求同时提供旧密码与新密码。"""

    old_password: str
    new_password: str

    @field_validator("old_password", "new_password")
    @classmethod
    def validate_password_length(cls, value: str, info: ValidationInfo) -> str:
        """校验修改密码字段长度，并返回中文规范提示。"""

        label = "当前密码" if info.field_name == "old_password" else "新密码"
        if len(value) < 8 or len(value) > 128:
            raise PydanticCustomError("password_length", "{label}长度必须为 8 到 128 位。", {"label": label})
        return value


class PreviewSizePresetUpdateRequest(BaseModel):
    """更新当前登录用户预设尺寸的入参。"""

    presets: list[PreviewSizePreset] = Field(default_factory=list, max_length=50)


class AuthUser(SchemaBase):
    """当前登录用户信息。"""

    id: int
    username: str
    display_name: str
    role: UserRole
    status: RecordStatus
    last_login_at: datetime | None
    preview_size_presets: list[PreviewSizePreset]


class LoginResponse(SchemaBase):
    """登录成功后的响应内容。"""

    user: AuthUser
