"""文件功能：定义项目级 app 配置结构，并提供 YAML 解析、生成与页面展示规格解析能力。"""

from __future__ import annotations

from typing import Literal, TypeAlias

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.exceptions import AppException

DEFAULT_PAGE_WIDTH = 1920
DEFAULT_PAGE_HEIGHT = 1080
DEFAULT_PROJECT_BASE_FONT_SIZE = "24px"


def build_default_style_spec_markdown(page_width: int, page_height: int, base_font_size: str) -> str:
    """按项目真实画布与基础字号生成建议性默认样式规范。"""

    return f"""> 本规范用于帮助页面创作、组件复用和 AI 生成保持统一的明亮商务风格。
> 本规范以建议为主，不要求所有页面使用相同结构，也不要求每页使用图片、图表或卡片。
> 当内容目标与某条建议冲突时，应优先保证信息表达清晰、阅读顺畅和视觉层级合理。
> 当前画布：{page_width} x {page_height} px；基础字号：{base_font_size}。

## 约束强度

- 必须遵守：固定画布、内容可读性、资源引用有效、文字层级清晰、主题色使用正确。
- 优先建议：统一间距、控制内容密度、保持视觉焦点、复用已有组件和资源。
- 可根据内容调整：页面分区、图片使用、列数、留白比例、图表形式和装饰方式。
- 应尽量避免：强行套用模板、为了填充空间堆砌内容、过度使用颜色或装饰。

## 整体视觉方向

- 保持明亮、专业、克制、清晰的商务风格，适合汇报、方案说明、产品介绍和数据解读。
- 优先使用白色、浅灰、雾蓝等明亮背景，以主题商务蓝作为主要视觉锚点。
- 深色区域、强调色、图片、图表和装饰都应服务于内容，不为了填充空间而增加视觉元素。
- 保持主题色、字体、间距、圆角和信息层级的一致性，但不要求页面使用相同的布局。

## 画布、留白与布局

- 页面四周建议保留 64px 到 80px 的安全边距；内容较密集时不建议低于 48px。
- 页面内部建议使用 8px 间距基线，常用间距优先选择 16px、24px、32px、48px 和 64px。
- 内容模块之间应保持清晰间距，并尽量形成统一的对齐关系。
- 可以使用单列、分栏、网格、上下分区、非对称布局或大面积留白，具体根据内容关系决定。
- 一般不建议超过三列并列主要内容；如果信息关系不清晰，应避免平均分栏。
- 每页建议有一个主要视觉焦点，可以是标题、结论、数字、图片、图表或其他视觉元素。

## 排版与信息层级

- 信息层级建议按照“页面标题 → 核心结论 → 模块标题 → 正文说明 → 辅助信息”组织。
- 页面标题应明确表达内容主题，避免只使用抽象或无信息量的标题。
- 核心结论可以通过字号、字重、颜色或独立区域突出，但不建议同时使用过多强调方式。
- 页面建议控制在三到四级文字层级以内。
- 普通页面标题建议使用基础字号的约 2.25 到 3.25 倍，模块标题建议使用基础字号的约 1.5 到 2.25 倍。
- 正文和辅助文字应保证在预览、截图和投影环境中的可读性。
- 内容过多时优先删减、重组或拆分，不要通过无限缩小字号来容纳内容。
- 列表、要点和说明应尽量简短，长段落应拆分为更易阅读的结构。

## 色彩与表面

- 优先使用主题提供的语义颜色，不在页面源码中随意增加新的品牌色。
- 普通页面建议使用一个主要强调色，必要时增加一个辅助强调色。
- 高饱和颜色适合用于重点数字、状态、标记或局部强调，不建议大面积同时使用多种鲜艳颜色。
- 深色背景上的文字应使用反色文字，并确保足够对比度。
- 卡片优先使用浅色表面、细边框和适度圆角，避免厚重阴影。
- 渐变、阴影、装饰线和背景纹理应保持克制。
- 选中、警告、增长、下降等状态不应只依赖颜色表达，必要时增加文字、图标、位置或形状辅助说明。

## 卡片与内容模块

- 卡片是常用的内容组织方式；使用卡片时，注意让高度、内边距和内容量相互匹配，避免卡片内部出现大片空白。
- 并列卡片可以保持统一尺寸，但不应为了等高拉伸明显较短的内容；出现较大空白时，优先调整卡片高度、内容分组或模块间距。
- 页面级留白可以用于形成节奏，但卡片内部明显且不必要的空白应优先复核布局和内容组织。

## 视觉素材选择

- 图片、图表、公式、示意图、图标和纯文字都是可选的表达方式，不要求每页使用视觉素材。
- 根据内容本身选择最合适的表达形式：需要展示对象时使用图片，需要表达数据关系时使用图表，需要表达公式或结构时使用对应的视觉形式。
- 视觉素材应与内容相关，并帮助观众理解、记忆或验证页面结论。
- 没有合适视觉素材时，可以使用纯文字、留白和排版建立视觉重点，不要强行添加装饰。
- 图文结合是可选的页面表达方式，不是默认页面模板。

## 组件与资源复用

- 页面骨架、信息卡、指标卡、图文模块和图表容器如果会跨页面重复，应优先复用已有组件。
- 创建页面或组件前，建议先检查项目和工作空间中是否已有合适的已发布组件。
- 资源、图片、图标和字体优先使用工作空间资产，减少重复上传和不可追踪的外部链接。
- 页面和组件应遵循已有组件契约，不要为了局部效果复制一套新的全局样式。
- Runtime 能力应使用已公开且带版本号的 Runtime Kit 能力。

## 页面节奏与变化

- 不要求每页使用图片、图表、卡片或分栏。
- 页面之间可以在信息密度、留白比例、焦点方式和布局结构上自然变化。
- 保持统一的是色彩角色、字号比例、间距尺度和信息层级，而不是每页的具体骨架。
- 连续使用相同结构时，应确认内容关系确实相似，避免所有页面都变成相同模板。
- 低信息量内容可以使用更多留白，高信息量内容应通过分组、对齐和层级降低阅读压力。

## 质量检查

- 页面是否能快速看出主题和核心结论？
- 标题、正文和辅助信息是否层级清晰？
- 内容是否过密，是否存在不必要的装饰？
- 颜色是否集中在主题角色内？
- 图片、图表或其他视觉元素是否真正帮助理解？
- 如果没有使用视觉素材，页面是否仍然完整、清晰、有节奏？
- 页面是否保持了主题一致性，同时避免模板化和重复感？"""


DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN = build_default_style_spec_markdown(
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
)
DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH = 2
MAX_PAGE_DIMENSION = 8192
DEFAULT_PROJECT_ICON = "slider"
DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON = True
ProjectMenuMode: TypeAlias = Literal["text", "preview", "bottom-preview"]
DEFAULT_PROJECT_MENU_MODE: ProjectMenuMode = "preview"


def normalize_project_base_font_size(value: object) -> object:
    """归一化项目基础字号，只接受 1-200 的整数像素值。"""

    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        raise ValueError("base_font_size 不能为空。")
    if normalized.endswith("px"):
        normalized = normalized[:-2].strip()
    if not normalized.isdigit():
        raise ValueError("base_font_size 仅支持正整数像素值，例如 24px。")
    numeric_value = int(normalized)
    if numeric_value < 1 or numeric_value > 200:
        raise ValueError("base_font_size 必须在 1-200px 之间。")
    return f"{numeric_value}px"


class ProjectAppPageConfig(BaseModel):
    """页面画布与显示规格配置，统一约束运行时预览、截图视口与页面默认视觉规格。"""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=DEFAULT_PAGE_WIDTH, gt=0, le=MAX_PAGE_DIMENSION)
    height: int = Field(default=DEFAULT_PAGE_HEIGHT, gt=0, le=MAX_PAGE_DIMENSION)
    baseFontSize: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32)
    iconDefaultStrokeWidth: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64)

    @field_validator("baseFontSize", mode="before")
    @classmethod
    def normalize_base_font_size(cls, value: object) -> object:
        """统一将基础字号规范为 px 字符串。"""

        return normalize_project_base_font_size(value)


class ProjectAppFeaturesConfig(BaseModel):
    """项目级应用功能开关。"""

    model_config = ConfigDict(extra="ignore")

    showPdfExportButton: bool | None = None
    menuMode: ProjectMenuMode | None = None


class ProjectAppSettings(BaseModel):
    """app.config.yaml 中的 app 节点。"""

    model_config = ConfigDict(extra="ignore")

    icon: str = DEFAULT_PROJECT_ICON
    title: str = ""
    description: str = ""
    features: ProjectAppFeaturesConfig = Field(default_factory=ProjectAppFeaturesConfig)
    page: ProjectAppPageConfig = Field(default_factory=ProjectAppPageConfig)


class ProjectAppConfigDocument(BaseModel):
    """项目级 app.config.yaml 文档结构。"""

    model_config = ConfigDict(extra="ignore")

    app: ProjectAppSettings = Field(default_factory=ProjectAppSettings)


def parse_project_app_config_document(yaml_text: str) -> ProjectAppConfigDocument:
    """解析并校验 app.config.yaml 文本。"""

    try:
        parsed_value = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise AppException(
            status_code=400,
            code="PROJECT_CONFIG_INVALID_YAML",
            detail=f"app.config.yaml YAML 语法错误：{exc}",
        ) from exc

    try:
        return ProjectAppConfigDocument.model_validate(parsed_value)
    except ValidationError as exc:
        raise AppException(
            status_code=400,
            code="PROJECT_CONFIG_INVALID_YAML",
            detail=f"app.config.yaml 配置结构不合法：{exc}",
        ) from exc


def build_project_app_config_document(
    *,
    title: str,
    description: str | None,
    icon: str | None,
    page_width: int,
    page_height: int,
    base_font_size: str = DEFAULT_PROJECT_BASE_FONT_SIZE,
    icon_default_stroke_width: int = DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    show_pdf_export_button: bool = DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    menu_mode: ProjectMenuMode = DEFAULT_PROJECT_MENU_MODE,
) -> ProjectAppConfigDocument:
    """基于项目结构化字段构造 Runtime 使用的 app 配置文档。"""

    return ProjectAppConfigDocument(
        app=ProjectAppSettings(
            icon=str(icon or "").strip() or DEFAULT_PROJECT_ICON,
            title=str(title or "").strip(),
            description=str(description or "").strip(),
            page=ProjectAppPageConfig(
                width=page_width,
                height=page_height,
                baseFontSize=base_font_size,
                iconDefaultStrokeWidth=icon_default_stroke_width,
            ),
            features=ProjectAppFeaturesConfig(
                showPdfExportButton=show_pdf_export_button,
                menuMode=menu_mode,
            ),
        )
    )


def dump_project_app_config_document_yaml(document: ProjectAppConfigDocument) -> str:
    """将项目 app 配置文档序列化为 Runtime 可消费的 YAML 文本。"""

    return yaml.safe_dump(
        document.model_dump(mode="python", exclude_none=True),
        allow_unicode=True,
        sort_keys=False,
    )


def resolve_project_page_config(yaml_text: str | None) -> ProjectAppPageConfig:
    """从 app.config.yaml 中解析页面尺寸；为空时回退到默认画布。"""

    if not str(yaml_text or "").strip():
        return ProjectAppPageConfig()
    return parse_project_app_config_document(str(yaml_text)).app.page
