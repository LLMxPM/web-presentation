"""文件功能：定义项目级 app 配置结构，并提供 YAML 解析、生成与页面展示规格解析能力。"""

from __future__ import annotations

from typing import Literal, TypeAlias

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.exceptions import AppException

DEFAULT_PAGE_WIDTH = 1920
DEFAULT_PAGE_HEIGHT = 1080
DEFAULT_PROJECT_BASE_FONT_SIZE = "20px"


def build_default_style_spec_markdown(page_width: int, page_height: int, base_font_size: str) -> str:
    """按项目真实画布与基础字号生成默认样式规范文本，作为布局数值基线。"""

    return f"""> 本规范是该项目的布局数值基线与页面类型约定；与平台通用规则（固定画布、根节点规则、资源引用规则等）冲突时以平台规则为准。
> 当前画布：{page_width} x {page_height} px；基础字号：{base_font_size}。

## 画布与留白

- 页面四周保留 48px 到 80px 安全边距；封面、章节页可适度放大以强化留白感，数据密集型页面可适当收紧但不低于 40px。
- 标题区应形成稳定位置，优先放在顶部或左上，不在不同页面间频繁跳动。
- 正文内容区优先使用 1 栏、2 栏或 3 栏布局；选择分栏数量时以信息量和视觉层级为依据——单一核心信息用 1 栏，并列对比用 2-3 栏，避免超过 3 个并列主信息块。
- 模块、卡片、图表之间保持适当视觉间距（建议 24px 到 48px），确保分组关系清晰而不松散。
- 页面应有明确视觉主次：标题、核心结论、证据内容、辅助说明依次递减。

## 组件与骨架使用

- 页面骨架（画布留白、标题区定位与样式、整体分区结构）由页面组件承担：项目建议组件中已有适合当前页型的已发布页面组件时优先使用，页面源码按其契约传入标题文本与正文内容，不重复设置页面级留白或重建标题结构。
- 没有合适的已发布页面组件且骨架会在多页复用时，先创建页面组件（根部使用 DefaultContainer，通过 props 或 slot 接收标题文本、默认 slot 接收正文），发布后更新项目 suggested_components。
- 确认只使用一次的页型，可直接使用 DefaultContainer 作为根节点，在页面源码中按本规范数值基线自行处理留白与标题区。
- 跨页重复的内容结构（如指标卡、信息卡、图表容器等）应抽取为内容组件，必须在 preview_schema.props 中声明尺寸控制字段，发布后更新项目 suggested_components；页面内小粒度复用元素使用原子组件，不需要尺寸控制字段。
- 项目 suggested_components 是复用基线——新建页面或组件前应先确认其中是否有适合的对象。

## 排版与层级

- 排版层级从高到低依次为：页面主标题 → 模块标题 → 正文内容 → 辅助说明（来源、注脚、图例等）。每一层级的字号应有明显跳跃，确保阅读时层级关系一目了然。
- 封面和章节页主标题应使用最大字号，形成强烈视觉锚点；普通内容页主标题应比模块标题明显更大。
- 正文使用可舒适阅读的字号，不应过大浪费空间也不应过小影响可读性；辅助文字明显小于正文，一般不低于 12px。
- 正文行高建议 1.5-1.75，标题行高建议 1.2-1.4；避免行高过大导致标题与正文间的视觉关联断裂。

## 页面类型参考

- 封面页：核心目标是建立第一印象和演讲主题认知。典型布局为垂直居中或左对齐的大标题区 + 副标题/日期/作者信息，可搭配品牌视觉或关键图形。信息密度低，留白充裕。
- 章节页：用于切换演讲主题段落。突出章节名称和一句导语，保持大面积留白以形成节奏停顿。信息密度最低，通常只有标题 + 一行导语。
- 目录页：展示 3 到 6 个章节的导航结构。可使用横向卡片、纵向列表或编号网格；避免写成长文本段落。
- 观点页：核心目标是让观众记住一个关键结论。使用大号结论句作为主视觉，下方补充 2 到 3 个简洁支撑点。不使用复杂图表或多层嵌套。
- 内容页：最常见的页面类型，标题区 + 主体内容区。主体可使用左右分栏（说明 + 图示）、三卡片并列或图文混排。根据内容的对比/递进/并列关系选择布局模式。
- 数据页：关键数字优先放大，图表必须配一句明确结论。合理选择图表类型以匹配数据关系（趋势用折线、对比用柱状、占比用饼图/环形图、分布用散点）。数据密集时优先拆分为多张数据页。
- 总结页：使用 3 到 5 个要点收束演讲，不引入新论据或复杂论证。可搭配关键结论回顾或行动号召。

## 内容密度

- 单页内容量应以观众在演讲节奏中能一次性接收为上限；内容过多时应拆页而非压缩排版密度。
- 列表项建议控制在 5 条以内，每条 1 到 2 行；超过此数量考虑分组展示或拆页。
- 表格列数过多时优先精简列或改为摘要卡片；行数过多时考虑分页或使用可读性更好的信息图替代。
- 图表页的核心是图表本身及其结论；单页复杂图表不超过 2 个，避免多个复杂图表互相干扰。"""


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
        raise ValueError("base_font_size 仅支持正整数像素值，例如 20px。")
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
