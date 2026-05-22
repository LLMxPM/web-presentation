"""文件功能：定义工作空间字体配置的请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RecordStatus


class WorkspaceFontConfigCreateRequest(BaseModel):
    """创建字体配置的请求模型。"""

    asset_id: int
    font_family: str = Field(min_length=1, max_length=255)
    font_format: str | None = Field(default=None, max_length=32)
    font_weight: str = Field(default="400", min_length=1, max_length=32)
    font_style: str = Field(default="normal", min_length=1, max_length=32)
    font_display: str = Field(default="swap", min_length=1, max_length=32)
    status: RecordStatus = RecordStatus.ACTIVE


class WorkspaceFontConfigUpdateRequest(BaseModel):
    """更新字体配置的请求模型。"""

    font_family: str | None = Field(default=None, min_length=1, max_length=255)
    font_format: str | None = Field(default=None, min_length=1, max_length=32)
    font_weight: str | None = Field(default=None, min_length=1, max_length=32)
    font_style: str | None = Field(default=None, min_length=1, max_length=32)
    font_display: str | None = Field(default=None, min_length=1, max_length=32)
    status: RecordStatus | None = None


class WorkspaceFontConfigResponse(BaseModel):
    """字体配置响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    asset_id: int
    asset_name: str
    font_family: str
    font_format: str
    font_weight: str
    font_style: str
    font_display: str
    status: RecordStatus
    asset_url: str | None = None
    created_at: datetime
    updated_at: datetime


class FontBundleItem(BaseModel):
    """预览配置中下发的单个字体注册项。"""

    asset_name: str
    font_family: str
    font_format: str
    font_weight: str
    font_style: str
    font_display: str


class FontBundleResponse(BaseModel):
    """运行时预加载字体配置包。"""

    items: dict[str, FontBundleItem] = Field(default_factory=dict)
