"""文件功能：定义项目与工作空间样式共享的展示配置快照、补丁和初始化来源。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.text_normalizer import normalize_text_to_lf
from app.schemas.component import SUGGESTED_COMPONENT_MAX_COUNT
from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_MENU_MODE,
    DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
    ProjectMenuMode,
    normalize_project_base_font_size,
)


class PresentationStyleModel(BaseModel):
    """为共享展示配置提供严格的额外字段约束。"""

    model_config = ConfigDict(extra="forbid")


def _normalize_theme_key(value: object) -> str | None:
    """把空白主题 key 归一化为未指定。"""

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class PresentationConfig(PresentationStyleModel):
    """项目和样式持久化时共用的完整展示配置。"""

    page_width: int = Field(default=DEFAULT_PAGE_WIDTH, ge=1, le=8192, description="页面画布宽度，单位为像素。")
    page_height: int = Field(default=DEFAULT_PAGE_HEIGHT, ge=1, le=8192, description="页面画布高度，单位为像素。")
    base_font_size: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32, description="项目基础字号，统一保存为 px 字符串。")
    icon_default_stroke_width: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64, description="图标默认描边宽度。")
    show_pdf_export_button: bool = Field(default=DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON, description="是否显示 PDF 导出按钮。")
    menu_mode: ProjectMenuMode = Field(default=DEFAULT_PROJECT_MENU_MODE, description="项目菜单展示模式。")
    theme_key: str | None = Field(default=None, min_length=1, max_length=64, description="工作空间内真实主题 key；未指定时固化默认主题。")
    style_spec_markdown: str = Field(default=DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN, description="供页面生成与编辑遵循的 Markdown 样式规范。")

    @field_validator("base_font_size", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)

    @field_validator("theme_key", mode="before")
    @classmethod
    def normalize_theme_key(cls, value: object) -> str | None:
        """去除主题 key 首尾空白。"""

        return _normalize_theme_key(value)

    @field_validator("style_spec_markdown", mode="before")
    @classmethod
    def normalize_style_spec_markdown(cls, value: object) -> str:
        """统一 Markdown 换行，None 按空文本处理。"""

        return normalize_text_to_lf(None if value is None else str(value))


class PresentationConfigPatch(PresentationStyleModel):
    """展示配置部分更新；显式 null 仅允许用于 theme_key。"""

    page_width: int | None = Field(default=None, ge=1, le=8192, description="新的页面画布宽度。")
    page_height: int | None = Field(default=None, ge=1, le=8192, description="新的页面画布高度。")
    base_font_size: str | None = Field(default=None, min_length=1, max_length=32, description="新的基础字号。")
    icon_default_stroke_width: int | None = Field(default=None, ge=1, le=64, description="新的图标默认描边宽度。")
    show_pdf_export_button: bool | None = Field(default=None, description="是否显示 PDF 导出按钮。")
    menu_mode: ProjectMenuMode | None = Field(default=None, description="新的项目菜单展示模式。")
    theme_key: str | None = Field(default=None, min_length=1, max_length=64, description="新的主题 key；null 表示使用工作空间默认主题。")
    style_spec_markdown: str | None = Field(default=None, description="新的完整 Markdown 样式规范；空字符串表示清空。")

    @field_validator("base_font_size", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)

    @field_validator("theme_key", mode="before")
    @classmethod
    def normalize_theme_key(cls, value: object) -> str | None:
        """去除主题 key 首尾空白。"""

        return _normalize_theme_key(value)

    @field_validator("style_spec_markdown", mode="before")
    @classmethod
    def normalize_style_spec_markdown(cls, value: object) -> str | None:
        """统一 Markdown 换行，保留 None 供字段缺失判断。"""

        if value is None:
            return None
        return normalize_text_to_lf(str(value))

    @model_validator(mode="after")
    def require_field(self) -> "PresentationConfigPatch":
        """拒绝不包含任何显式展示字段的空补丁。"""

        if not self.model_fields_set:
            raise ValueError("presentation 至少需要提供一个待修改字段。")
        invalid_null_fields = [
            field_name
            for field_name in self.model_fields_set
            if field_name != "theme_key" and getattr(self, field_name) is None
        ]
        if invalid_null_fields:
            raise ValueError(f"以下展示字段不能为 null：{', '.join(sorted(invalid_null_fields))}。")
        return self


class SuggestedComponentsSelection(PresentationStyleModel):
    """有序建议组件选择；空数组表示清空。"""

    component_ids: list[int] = Field(default_factory=list, max_length=SUGGESTED_COMPONENT_MAX_COUNT, description="有序建议组件 ID；完整替换并按顺序去重，空数组表示清空。")

    @field_validator("component_ids")
    @classmethod
    def normalize_component_ids(cls, values: list[int]) -> list[int]:
        """按输入顺序去重并拒绝非正整数 ID。"""

        result: list[int] = []
        seen: set[int] = set()
        for value in values:
            component_id = int(value)
            if component_id <= 0:
                raise ValueError("component_ids 只能包含正整数。")
            if component_id not in seen:
                seen.add(component_id)
                result.append(component_id)
        return result


class StyleConfiguration(PresentationStyleModel):
    """完整样式快照，供样式创建和项目自定义初始化使用。"""

    presentation: PresentationConfig = Field(default_factory=PresentationConfig, description="完整展示配置。")
    suggested_components: SuggestedComponentsSelection = Field(default_factory=SuggestedComponentsSelection, description="完整建议组件选择。")


class StyleConfigurationPatch(PresentationStyleModel):
    """样式快照补丁；建议组件一旦出现即执行完整替换。"""

    presentation: PresentationConfigPatch | None = Field(default=None, description="仅修改显式提交的展示字段。")
    suggested_components: SuggestedComponentsSelection | None = Field(default=None, description="出现时完整替换建议组件集合。")

    @model_validator(mode="after")
    def require_section(self) -> "StyleConfigurationPatch":
        """拒绝没有 presentation 或 suggested_components 的空配置。"""

        if self.presentation is None and self.suggested_components is None:
            raise ValueError("configuration 至少需要提供 presentation 或 suggested_components。")
        return self


class ProjectDefaultConfiguration(PresentationStyleModel):
    """使用工作空间 default 样式初始化项目。"""

    mode: Literal["default"] = Field(default="default", description="使用工作空间 default 样式。")


class ProjectStyleConfiguration(PresentationStyleModel):
    """使用指定工作空间样式初始化或覆盖项目。"""

    mode: Literal["style"] = Field(description="使用指定工作空间样式。")
    style_id: int = Field(gt=0, description="当前工作空间内 active 样式 ID。")


class ProjectCustomConfiguration(StyleConfiguration):
    """使用显式完整配置初始化项目。"""

    mode: Literal["custom"] = Field(description="使用显式自定义配置。")


ProjectCreateConfiguration = Annotated[
    ProjectDefaultConfiguration | ProjectStyleConfiguration | ProjectCustomConfiguration,
    Field(discriminator="mode"),
]


class ProjectPatchConfiguration(StyleConfigurationPatch):
    """部分修改项目已有样式快照。"""

    mode: Literal["patch"] = Field(description="部分修改现有项目样式快照。")


ProjectUpdateConfiguration = Annotated[
    ProjectPatchConfiguration | ProjectStyleConfiguration,
    Field(discriminator="mode"),
]
