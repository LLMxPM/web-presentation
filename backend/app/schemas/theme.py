"""文件功能：定义工作空间主题库的请求、响应与调色板结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.platform_fonts import MONO_FONT_PRESETS, SANS_FONT_PRESETS
from app.schemas.asset import AssetAnalysisMetadata


def _normalize_theme_key(value: object) -> object:
    """归一化主题 key，兼容用户输入的大写与首尾空白。"""

    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower()
    return value


class ThemeTextPalette(BaseModel):
    """主题文字色板。"""

    primary: str = Field(min_length=1, max_length=64)
    secondary: str = Field(min_length=1, max_length=64)
    invert: str = Field(min_length=1, max_length=64)


class ThemeBackgroundPalette(BaseModel):
    """主题背景色板。"""

    default: str = Field(min_length=1, max_length=64)
    invert: str = Field(min_length=1, max_length=64)


class ThemeBorderPalette(BaseModel):
    """主题边框色板。"""

    default: str = Field(min_length=1, max_length=64)
    subtle: str = Field(min_length=1, max_length=64)


class ThemeLinkPalette(BaseModel):
    """主题链接色板。"""

    default: str = Field(min_length=1, max_length=64)
    hover: str = Field(min_length=1, max_length=64)
    visited: str = Field(min_length=1, max_length=64)


class ThemePalette(BaseModel):
    """主题总色板结构。"""

    text: ThemeTextPalette
    background: ThemeBackgroundPalette
    border: ThemeBorderPalette
    link: ThemeLinkPalette
    accent: list[str] = Field(min_length=1, max_length=12)

    @field_validator("accent")
    @classmethod
    def validate_accent(cls, value: list[str]) -> list[str]:
        """确保强调色数组内没有空值。"""

        normalized_values = [str(item).strip() for item in value]
        if not all(normalized_values):
            raise ValueError("accent 颜色列表不能为空值。")
        return normalized_values


class WorkspaceThemeBaseRequest(BaseModel):
    """工作空间主题写入请求的公共字段。"""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    logo_asset_id: int | None = None
    invert_logo_asset_id: int | None = None
    project_icon_asset_id: int | None = None
    heading_font_family_id: int | None = None
    body_font_family_id: int | None = None
    code_font_family_id: int | None = None
    heading_font_preset: str | None = None
    body_font_preset: str | None = None
    code_font_preset: str | None = None
    palette: ThemePalette

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将主题 key 归一化为小写，减少编辑时的格式摩擦。"""

        return _normalize_theme_key(value)

    @model_validator(mode="after")
    def validate_font_sources(self) -> "WorkspaceThemeBaseRequest":
        """校验每个字体槽只能选择工作空间字体族或受支持的内置预设。"""

        _validate_font_source("标题", self.heading_font_family_id, self.heading_font_preset, SANS_FONT_PRESETS)
        _validate_font_source("正文", self.body_font_family_id, self.body_font_preset, SANS_FONT_PRESETS)
        _validate_font_source("代码", self.code_font_family_id, self.code_font_preset, MONO_FONT_PRESETS)
        return self


class WorkspaceThemeCreateRequest(WorkspaceThemeBaseRequest):
    """创建主题请求。"""


class WorkspaceThemeUpdateRequest(BaseModel):
    """更新主题请求。"""

    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    logo_asset_id: int | None = None
    invert_logo_asset_id: int | None = None
    project_icon_asset_id: int | None = None
    heading_font_family_id: int | None = None
    body_font_family_id: int | None = None
    code_font_family_id: int | None = None
    heading_font_preset: str | None = None
    body_font_preset: str | None = None
    code_font_preset: str | None = None
    palette: ThemePalette | None = None

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将主题 key 归一化为小写，减少编辑时的格式摩擦。"""

        return _normalize_theme_key(value)

    @model_validator(mode="after")
    def validate_font_sources(self) -> "WorkspaceThemeUpdateRequest":
        """校验显式传入的字体族和内置预设不会互相冲突。"""

        _validate_font_source("标题", self.heading_font_family_id, self.heading_font_preset, SANS_FONT_PRESETS)
        _validate_font_source("正文", self.body_font_family_id, self.body_font_preset, SANS_FONT_PRESETS)
        _validate_font_source("代码", self.code_font_family_id, self.code_font_preset, MONO_FONT_PRESETS)
        return self


class WorkspaceThemeCopyRequest(BaseModel):
    """复制主题请求。"""

    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value: object) -> object:
        """统一将主题 key 归一化为小写，减少复制时的格式摩擦。"""

        return _normalize_theme_key(value)


class WorkspaceThemeAssetSummary(BaseModel):
    """主题响应中的资产摘要。"""

    id: int
    name: str
    original_name: str
    asset_type: str
    analysis_metadata: AssetAnalysisMetadata | None = None
    url: str | None = None


class WorkspaceThemeFontFamilySummary(BaseModel):
    """主题响应中的字体族摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class WorkspaceThemeItem(BaseModel):
    """工作空间主题响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    key: str
    name: str
    description: str | None
    logo_asset_id: int | None
    invert_logo_asset_id: int | None
    project_icon_asset_id: int | None
    project_icon_name: str | None
    heading_font_family_id: int | None
    body_font_family_id: int | None
    code_font_family_id: int | None
    heading_font_label: str | None = None
    body_font_label: str | None = None
    code_font_label: str | None = None
    heading_font_preset: str | None = None
    body_font_preset: str | None = None
    code_font_preset: str | None = None
    palette: ThemePalette
    logo_asset: WorkspaceThemeAssetSummary | None = None
    invert_logo_asset: WorkspaceThemeAssetSummary | None = None
    project_icon_asset: WorkspaceThemeAssetSummary | None = None
    heading_font_family: WorkspaceThemeFontFamilySummary | None = None
    body_font_family: WorkspaceThemeFontFamilySummary | None = None
    code_font_family: WorkspaceThemeFontFamilySummary | None = None
    resolved_theme_config_yaml: str
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


def _validate_font_source(
    slot_name: str,
    family_id: int | None,
    preset: str | None,
    allowed_presets: frozenset[str],
) -> None:
    """验证单个字体槽的来源和值域，避免主题配置生成不可控 CSS 字体名。"""

    normalized_preset = str(preset or "").strip()
    if family_id is not None and normalized_preset:
        raise ValueError(f"{slot_name}字体不能同时选择字体族和内置预设。")
    if normalized_preset and normalized_preset not in allowed_presets:
        raise ValueError(f"{slot_name}字体预设不受支持。")
