"""文件功能：定义用户级预设尺寸 JSON 的结构、默认值与校验工具。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.exceptions import AppException


class PreviewSizePreset(BaseModel):
    """用户可维护的预览尺寸规格预设。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    width: int = Field(ge=1, le=8192)
    height: int = Field(ge=1, le=8192)
    base_font_size: str = Field(default="20px", min_length=1, max_length=16)
    icon_default_stroke_width: int = Field(default=2, ge=1, le=64)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """清理名称首尾空白，避免保存空白名称。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("名称不能为空。")
        return normalized

    @field_validator("base_font_size")
    @classmethod
    def normalize_base_font_size(cls, value: str) -> str:
        """归一化基础字号为 px 字符串。"""

        normalized = value.strip().lower()
        if normalized.endswith("px"):
            number_text = normalized[:-2]
        else:
            number_text = normalized
        if not number_text.isdigit():
            raise ValueError("基础字号必须是 px 数值。")
        number_value = int(number_text)
        if number_value < 1 or number_value > 200:
            raise ValueError("基础字号必须在 1px 到 200px 之间。")
        return f"{number_value}px"


DEFAULT_PREVIEW_SIZE_PRESETS: list[dict[str, int | str]] = [
    {
        "name": "桌面 16:9",
        "width": 1920,
        "height": 1080,
        "base_font_size": "20px",
        "icon_default_stroke_width": 2,
    },
    {
        "name": "桌面 16:9 小屏",
        "width": 1600,
        "height": 900,
        "base_font_size": "20px",
        "icon_default_stroke_width": 2,
    },
    {
        "name": "笔记本",
        "width": 1366,
        "height": 768,
        "base_font_size": "20px",
        "icon_default_stroke_width": 2,
    },
    {
        "name": "手机竖屏",
        "width": 1080,
        "height": 1920,
        "base_font_size": "28px",
        "icon_default_stroke_width": 3,
    },
    {
        "name": "手机竖屏小屏",
        "width": 750,
        "height": 1334,
        "base_font_size": "24px",
        "icon_default_stroke_width": 3,
    },
]


class PreviewSizePresetUpdateRequest(BaseModel):
    """更新当前用户预设尺寸的入参。"""

    model_config = ConfigDict(extra="forbid")

    presets: list[PreviewSizePreset] = Field(default_factory=list, max_length=50)


def build_default_preview_size_presets() -> list[dict[str, int | str]]:
    """返回系统内置的用户预设尺寸规格列表。"""

    return [dict(item) for item in DEFAULT_PREVIEW_SIZE_PRESETS]


def validate_preview_size_presets(value: object) -> list[dict[str, int | str]]:
    """校验并归一化用户级预设尺寸规格 JSON。"""

    if value is None:
        return build_default_preview_size_presets()
    if not isinstance(value, list):
        raise AppException(status_code=400, code="PREVIEW_SIZE_PRESETS_INVALID", detail="预设尺寸必须是数组。")

    try:
        request = PreviewSizePresetUpdateRequest(presets=value)
    except ValidationError as exc:
        raise AppException(status_code=400, code="PREVIEW_SIZE_PRESETS_INVALID", detail=f"预设尺寸结构错误：{exc}") from exc

    return [item.model_dump(mode="python") for item in request.presets]
