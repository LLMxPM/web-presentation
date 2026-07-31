"""文件功能：定义工作空间字体族与字体文件（face）的请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RecordStatus


class WorkspaceFontConfigCreateRequest(BaseModel):
    """创建字体文件配置的请求模型，按 family 名归属（不存在时自动创建）。"""

    asset_id: int
    family_name: str = Field(min_length=1, max_length=255)
    font_format: str | None = Field(default=None, max_length=32)
    font_weight: str = Field(default="400", min_length=1, max_length=32)
    font_style: str = Field(default="normal", min_length=1, max_length=32)
    font_display: str = Field(default="swap", min_length=1, max_length=32)
    status: RecordStatus = RecordStatus.ACTIVE


class WorkspaceFontConfigUpdateRequest(BaseModel):
    """更新字体文件配置的请求模型；修改 family_name 即把 face 移动到目标字体族。"""

    family_name: str | None = Field(default=None, min_length=1, max_length=255)
    font_format: str | None = Field(default=None, min_length=1, max_length=32)
    font_weight: str | None = Field(default=None, min_length=1, max_length=32)
    font_style: str | None = Field(default=None, min_length=1, max_length=32)
    font_display: str | None = Field(default=None, min_length=1, max_length=32)
    status: RecordStatus | None = None


class WorkspaceFontConfigResponse(BaseModel):
    """字体文件配置响应模型，font_family 由所属字体族名派生。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    family_id: int
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


class WorkspaceFontFamilyUpdateRequest(BaseModel):
    """重命名字体族的请求模型。"""

    name: str = Field(min_length=1, max_length=255)


class WorkspaceFontFamilyResponse(BaseModel):
    """字体族响应模型，内嵌该族全部字体文件（face）。"""

    id: int
    workspace_id: int
    name: str
    faces: list[WorkspaceFontConfigResponse] = Field(default_factory=list)
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
