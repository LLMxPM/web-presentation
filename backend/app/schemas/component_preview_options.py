"""文件功能：定义组件预览页面尺寸、主题与组件占位配置。"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    normalize_project_base_font_size,
)

ComponentPreviewSizeMode = Literal["auto", "percent", "fixed"]
ComponentPreviewAlignment = Literal["start", "center", "end"]


class ComponentPreviewPageOptions(BaseModel):
    """组件预览页面配置，直接决定 Runtime 页面尺寸与主题。"""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=DEFAULT_PAGE_WIDTH, ge=1, le=8192)
    height: int = Field(default=DEFAULT_PAGE_HEIGHT, ge=1, le=8192)
    base_font_size: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32)
    icon_default_stroke_width: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64)
    theme_key: str | None = Field(default=None, min_length=1, max_length=64)
    theme_config_yaml: str | None = None

    @model_validator(mode="after")
    def validate_visual_specs(self) -> "ComponentPreviewPageOptions":
        """归一化页面默认视觉规格。"""

        self.base_font_size = str(normalize_project_base_font_size(self.base_font_size))
        return self


class ComponentPreviewPlacementOptions(BaseModel):
    """组件在预览页面中的占位与对齐配置。"""

    model_config = ConfigDict(extra="forbid")

    width_mode: ComponentPreviewSizeMode = "percent"
    width_value: int | None = Field(default=100, ge=1, le=8192)
    height_mode: ComponentPreviewSizeMode = "auto"
    height_value: int | None = Field(default=None, ge=1, le=8192)
    horizontal_align: ComponentPreviewAlignment = "center"
    vertical_align: ComponentPreviewAlignment = "center"
    padding: int = Field(default=48, ge=0, le=512)

    @model_validator(mode="after")
    def validate_size_values(self) -> Self:
        """按宽高模式校验数值范围，并清理 auto 模式下的无效数值。"""

        self.width_value = normalize_size_value(self.width_mode, self.width_value, default_value=100)
        self.height_value = normalize_size_value(self.height_mode, self.height_value, default_value=None)
        return self


class ComponentPreviewOptions(BaseModel):
    """组件预览 artifact 创建选项。"""

    model_config = ConfigDict(extra="forbid")

    page: ComponentPreviewPageOptions = Field(default_factory=ComponentPreviewPageOptions)
    placement: ComponentPreviewPlacementOptions = Field(default_factory=ComponentPreviewPlacementOptions)


def build_default_component_preview_options(default_theme_key: str | None = None) -> ComponentPreviewOptions:
    """基于工作空间默认主题构造组件预览默认选项。"""

    return ComponentPreviewOptions(page=ComponentPreviewPageOptions(theme_key=default_theme_key))


def normalize_size_value(
    size_mode: ComponentPreviewSizeMode,
    value: int | None,
    *,
    default_value: int | None,
) -> int | None:
    """按尺寸模式归一化占位宽高数值。"""

    if size_mode == "auto":
        return None
    if value is None:
        value = default_value
    if value is None:
        return None
    if size_mode == "percent":
        return min(100, max(1, value))
    return min(8192, max(1, value))
