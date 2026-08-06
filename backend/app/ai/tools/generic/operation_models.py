"""文件功能：定义内容助手通用业务操作的精确参数模型，供操作手册与运行时校验共同复用。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.tools.shared import SourceEditInput
from app.models.enums import AssetType, RecordStatus, WorkspaceComponentType
from app.schemas.project import ProjectBuildExtraAssetsConfig
from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
    ProjectMenuMode,
)
from app.schemas.project_route import ProjectRouteItemWrite
from app.schemas.theme import ThemePalette


class OperationArgumentsModel(BaseModel):
    """操作参数基础模型，拒绝手册未声明的额外字段。"""

    model_config = ConfigDict(extra="forbid")


class EmptyArguments(OperationArgumentsModel):
    """不接受额外参数的操作。"""


class CommonListFilters(OperationArgumentsModel):
    """项目、主题和样式列表通用筛选参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始。")
    page_size: int = Field(default=50, ge=1, le=100, description="每页数量，最大 100。")
    keyword: str | None = Field(default=None, description="按名称或描述进行模糊搜索的关键词。")
    status: RecordStatus | None = Field(default=None, description="记录状态；不传时使用该对象的默认可见范围。")
    sort_by: str = Field(default="updated_at", description="排序字段，通常使用 updated_at。")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="排序方向。")


class ArchivedListFilters(CommonListFilters):
    """允许显式包含归档记录的列表筛选参数。"""

    include_archived: bool = Field(default=False, description="是否同时返回归档记录。")


class ArchivedDetailOptions(OperationArgumentsModel):
    """主题或样式详情读取的归档可见性选项。"""

    include_archived: bool = Field(default=False, description="是否允许读取已归档的目标对象。")


class PageListFilters(CommonListFilters):
    """页面列表筛选参数。"""

    project_id: int | None = Field(default=None, ge=1, description="可选项目 ID；必须属于当前工作空间和本轮项目工作集。")


class ProjectStyleConfigFilters(OperationArgumentsModel):
    """项目样式配置查询参数。"""

    include_style_spec_markdown: bool = Field(
        default=False,
        description="是否返回可能较长的 Markdown 样式规范全文；仅确需编辑或审阅时设为 true。",
    )


class ComponentListFilters(OperationArgumentsModel):
    """组件列表筛选参数。"""

    component_type: WorkspaceComponentType | None = Field(default=None, description="组件分类。")
    keyword: str | None = Field(default=None, description="按组件名称、引用名或摘要搜索。")
    project_id: int | None = Field(default=None, ge=1, description="scope=suggested 时使用的目标项目 ID；不传时使用当前焦点项目。")
    scope: Literal["all", "suggested"] = Field(default="all", description="all 查询工作空间组件库；suggested 查询项目建议组件。")
    limit: int = Field(default=50, ge=1, le=100, description="最多返回的组件数量。")


class AssetListFilters(OperationArgumentsModel):
    """资源列表筛选参数。"""

    asset_type: AssetType | None = Field(default=None, description="资源类型。")
    tag: str | None = Field(default=None, description="要求资源包含的单个标签。")
    keyword: str | None = Field(default=None, description="按资源名称或描述搜索。")
    project_id: int | None = Field(default=None, ge=1, description="scope=suggested 时使用的目标项目 ID；不传时使用当前焦点项目。")
    scope: Literal["suggested", "all"] = Field(
        default="suggested",
        description="suggested 优先返回当前项目建议资源；all 查询工作空间全部 active 资源。",
    )
    limit: int = Field(default=50, ge=1, le=100, description="最多返回的资源数量。")


class RuntimeKitListFilters(OperationArgumentsModel):
    """Runtime Kit 能力目录筛选参数。"""

    kind: Literal["component", "composable", "util", "type"] | None = Field(default=None, description="能力类型。")
    base_name: str | None = Field(default=None, description="不含版本后缀的能力基础名称。")
    version_no: int | None = Field(default=None, ge=1, description="指定公开能力版本号。")
    include_all_versions: bool = Field(default=False, description="是否返回同一能力的全部公开版本。")
    keyword: str | None = Field(default=None, description="按名称、说明或分类搜索。")
    category: str | None = Field(default=None, description="能力目录分类。")
    limit: int = Field(default=50, ge=1, le=100, description="最多返回的能力数量。")


class RuntimeKitDetailFilters(OperationArgumentsModel):
    """Runtime Kit 单项详情查询参数。"""

    name: str = Field(min_length=1, description="带版本的公开能力名称，例如 MetricCard.v1。")
    kind: Literal["component", "composable", "util", "type"] | None = Field(default=None, description="可选能力类型，用于消除同名歧义。")


class FontListFilters(OperationArgumentsModel):
    """已注册字体资源筛选参数。"""

    keyword: str | None = Field(default=None, description="按资源名称搜索。")
    description_keyword: str | None = Field(default=None, description="按资源描述搜索。")
    tags: list[str] | None = Field(default=None, description="要求字体资源同时包含的标签。")
    limit: int = Field(default=20, ge=1, le=100, description="最多返回的字体数量。")


class ProjectCreatePayload(OperationArgumentsModel):
    """创建项目的模型可写字段。"""

    name: str = Field(min_length=1, max_length=128, description="项目名称。")
    description: str | None = Field(default=None, max_length=2000, description="项目用途或内容范围说明。")
    page_width: int = Field(default=DEFAULT_PAGE_WIDTH, ge=1, le=8192, description="页面画布宽度，单位为像素。")
    page_height: int = Field(default=DEFAULT_PAGE_HEIGHT, ge=1, le=8192, description="页面画布高度，单位为像素。")
    base_font_size: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32, description="项目基础字号，推荐使用 px 字符串。")
    icon_default_stroke_width: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64, description="图标默认描边宽度。")
    show_pdf_export_button: bool = Field(default=True, description="预览界面是否显示 PDF 导出按钮。")
    menu_mode: ProjectMenuMode = Field(default="preview", description="项目菜单展示模式。")
    theme_key: str | None = Field(default=None, min_length=1, max_length=64, description="当前工作空间已存在的主题 key。")
    style_spec_markdown: str = Field(default=DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN, description="供页面生成和编辑遵循的 Markdown 样式规范。")
    build_extra_assets_json: ProjectBuildExtraAssetsConfig | None = Field(default=None, description="构建时需要额外打包的工作空间资源名称。")
    suggested_component_source_style_id: int | None = Field(default=None, ge=1, description="用于初始化建议组件的工作空间样式 ID。")


class ProjectUpdatePayload(OperationArgumentsModel):
    """修改项目元数据和受控展示配置的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的项目名称。")
    description: str | None = Field(default=None, max_length=2000, description="新的项目说明。")
    page_width: int | None = Field(default=None, ge=1, le=8192, description="新的页面画布宽度。")
    page_height: int | None = Field(default=None, ge=1, le=8192, description="新的页面画布高度。")
    base_font_size: str | None = Field(default=None, min_length=1, max_length=32, description="新的基础字号。")
    icon_default_stroke_width: int | None = Field(default=None, ge=1, le=64, description="新的图标默认描边宽度。")
    show_pdf_export_button: bool | None = Field(default=None, description="是否显示 PDF 导出按钮。")
    menu_mode: ProjectMenuMode | None = Field(default=None, description="新的菜单展示模式。")
    theme_key: str | None = Field(default=None, min_length=1, max_length=64, description="新的主题 key。")
    style_spec_markdown: str | None = Field(default=None, description="新的 Markdown 样式规范。")
    build_extra_assets_json: ProjectBuildExtraAssetsConfig | None = Field(default=None, description="新的构建额外资源配置。")
    suggested_component_source_style_id: int | None = Field(default=None, ge=1, description="新的建议组件来源样式 ID。")


class PageCreatePayload(OperationArgumentsModel):
    """创建 Vue 页面参数。"""

    project_id: int = Field(gt=0, description="目标项目 ID；必须属于当前工作空间和本轮项目工作集。")
    title: str = Field(min_length=1, max_length=128, description="页面标题。")
    page_content: str = Field(min_length=1, description="完整、可编译的 Vue 单文件组件源码。")
    summary: str | None = Field(default=None, max_length=500, description="页面内容摘要。")
    speaker_notes: str | None = Field(default=None, max_length=10000, description="演讲者备注。")


class PageMetadataPayload(OperationArgumentsModel):
    """页面元数据修改参数。"""

    title: str | None = Field(default=None, min_length=1, max_length=128, description="新的页面标题。")
    summary: str | None = Field(default=None, max_length=500, description="新的页面摘要；空字符串表示清空。")
    speaker_notes: str | None = Field(default=None, max_length=10000, description="新的演讲者备注；空字符串表示清空。")
    change_note: str | None = Field(default=None, max_length=255, description="本次修改说明。")


class PageContentPayload(OperationArgumentsModel):
    """页面源码结构化修改参数。"""

    edits: list[SourceEditInput] = Field(min_length=1, description="按顺序应用的结构化源码编辑；定位文本必须来自最新页面源码。")
    base_version_no: int = Field(ge=1, description="读取页面源码时得到的当前版本号，用于防止覆盖并发修改。")
    change_note: str | None = Field(default=None, max_length=255, description="本次源码修改说明。")


class ComponentCreatePayload(OperationArgumentsModel):
    """创建组件草稿参数。"""

    name: str = Field(min_length=1, max_length=128, description="组件展示名称。")
    import_name: str = Field(min_length=1, max_length=128, description="Vue 源码中的组件引用名，使用合法 PascalCase 标识符。")
    content: str = Field(min_length=1, description="完整、可编译的 Vue 单文件组件源码。")
    component_type: WorkspaceComponentType = Field(default=WorkspaceComponentType.CONTENT_COMPONENT, description="组件分类。")
    summary: str | None = Field(default=None, max_length=500, description="组件职责和使用场景摘要。")
    preview_schema: str | dict[str, Any] | None = Field(default=None, description="组件预览参数 Schema，可传 JSON 对象或等价 JSON 字符串。")
    change_note: str | None = Field(default=None, max_length=255, description="初始草稿说明。")


class ComponentMetadataPayload(OperationArgumentsModel):
    """组件元数据修改参数。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的组件展示名称。")
    import_name: str | None = Field(default=None, min_length=1, max_length=128, description="新的 PascalCase 引用名。")
    component_type: WorkspaceComponentType | None = Field(default=None, description="新的组件分类。")
    summary: str | None = Field(default=None, max_length=500, description="新的组件摘要。")
    preview_schema: str | dict[str, Any] | None = Field(default=None, description="新的预览参数 Schema。")
    change_note: str | None = Field(default=None, max_length=255, description="本次修改说明。")


class ComponentContentPayload(OperationArgumentsModel):
    """组件源码结构化修改参数。"""

    edits: list[SourceEditInput] = Field(min_length=1, description="按顺序应用的结构化源码编辑。")
    base_draft_hash: str = Field(min_length=1, description="读取组件详情时得到的当前草稿 SHA-256 指纹。")
    base_published_version_no: int = Field(ge=0, description="读取组件详情时得到的草稿基线发布版本号。")
    change_note: str | None = Field(default=None, max_length=255, description="本次源码修改说明。")


EditableAssetType = Literal["icon", "drawio", "mermaid", "chart", "formula"]


class AssetCreatePayload(OperationArgumentsModel):
    """创建可编辑文本资源参数。"""

    asset_type: EditableAssetType = Field(description="可创建的文本资源类型；不支持 image、video 或 font。")
    name: str = Field(min_length=1, description="工作空间内引用资源使用的稳定名称。")
    original_name: str = Field(min_length=1, description="带合适扩展名的展示文件名。")
    content: str = Field(description="资源的完整文本内容。")
    description: str | None = Field(default=None, description="资源用途说明。")
    tags: list[str] | str | None = Field(default=None, description="标签数组，或兼容的逗号分隔字符串。")
    approx_aspect_ratio: str | None = Field(default=None, description="近似宽高比，例如 16:9。")


class AssetMetadataPayload(OperationArgumentsModel):
    """资源元数据修改参数。"""

    name: str | None = Field(default=None, min_length=1, description="新的稳定资源名。")
    original_name: str | None = Field(default=None, min_length=1, description="新的展示文件名。")
    description: str | None = Field(default=None, description="新的资源说明。")
    tags: list[str] | str | None = Field(default=None, description="替换后的标签。")
    approx_aspect_ratio: str | None = Field(default=None, description="新的近似宽高比。")
    clear_approx_aspect_ratio: bool = Field(default=False, description="是否明确清除已有近似宽高比；与 approx_aspect_ratio 不要同时使用。")


class AssetContentPayload(OperationArgumentsModel):
    """资源内容写入参数。"""

    content: str = Field(description="要写入的完整资源文本内容。")
    change_note: str | None = Field(default=None, description="本次内容修改说明。")


class ThemeCreatePayload(OperationArgumentsModel):
    """限制内容助手创建主题时只能提交文本与色板字段。"""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="主题稳定 key，只能包含小写字母、数字、下划线和短横线。")
    name: str = Field(min_length=1, max_length=128, description="主题展示名称。")
    description: str | None = Field(default=None, max_length=2000, description="主题用途和视觉特征说明。")
    palette: ThemePalette = Field(description="完整主题色板；文字、背景、边框、链接和强调色均必须提供。")


class ThemeUpdatePayload(OperationArgumentsModel):
    """限制内容助手修改主题时不能接触 Logo 和字体字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的主题名称。")
    description: str | None = Field(default=None, max_length=2000, description="新的主题说明。")
    palette: ThemePalette | None = Field(default=None, description="完整替换后的主题色板。")


class StyleCreatePayload(OperationArgumentsModel):
    """创建工作空间样式模板参数。"""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="样式稳定 key。")
    name: str = Field(min_length=1, max_length=128, description="样式展示名称。")
    description: str | None = Field(default=None, max_length=2000, description="样式用途说明。")
    page_width: int = Field(default=DEFAULT_PAGE_WIDTH, ge=1, le=8192, description="页面画布宽度。")
    page_height: int = Field(default=DEFAULT_PAGE_HEIGHT, ge=1, le=8192, description="页面画布高度。")
    base_font_size: str = Field(default=DEFAULT_PROJECT_BASE_FONT_SIZE, min_length=1, max_length=32, description="基础字号。")
    icon_default_stroke_width: int = Field(default=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH, ge=1, le=64, description="图标默认描边宽度。")
    show_pdf_export_button: bool = Field(default=True, description="是否显示 PDF 导出按钮。")
    menu_mode: ProjectMenuMode = Field(default="preview", description="菜单展示模式。")
    theme_key: str | None = Field(default=None, min_length=1, max_length=64, description="关联主题 key。")
    style_spec_markdown: str = Field(default=DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN, description="Markdown 样式规范。")


class StyleUpdatePayload(OperationArgumentsModel):
    """修改工作空间样式模板参数。"""

    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="新的样式 key。")
    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的样式名称。")
    description: str | None = Field(default=None, max_length=2000, description="新的样式说明。")
    page_width: int | None = Field(default=None, ge=1, le=8192, description="新的画布宽度。")
    page_height: int | None = Field(default=None, ge=1, le=8192, description="新的画布高度。")
    base_font_size: str | None = Field(default=None, min_length=1, max_length=32, description="新的基础字号。")
    icon_default_stroke_width: int | None = Field(default=None, ge=1, le=64, description="新的图标描边宽度。")
    show_pdf_export_button: bool | None = Field(default=None, description="是否显示 PDF 导出按钮。")
    menu_mode: ProjectMenuMode | None = Field(default=None, description="新的菜单展示模式。")
    theme_key: str | None = Field(default=None, min_length=1, max_length=64, description="新的主题 key。")
    style_spec_markdown: str | None = Field(default=None, description="新的 Markdown 样式规范。")


class RestorePayload(OperationArgumentsModel):
    """恢复归档对象的可选参数。"""

    reason: str | None = Field(default=None, max_length=1000, description="恢复原因。")


class ComponentPublishPayload(OperationArgumentsModel):
    """发布组件草稿参数。"""

    release_name: str | None = Field(default=None, description="可选发布版本名称。")
    change_note: str | None = Field(default=None, description="发布说明。")


class PageCheckPayload(OperationArgumentsModel):
    """页面候选代码检查参数。"""

    content: str | None = Field(default=None, description="待检查的完整页面源码；不传时检查 target_id 对应页面当前源码。")
    edits: list[SourceEditInput] | None = Field(default=None, description="应用到现有页面源码后再检查的结构化 edits。")


class ComponentCheckPayload(PageCheckPayload):
    """组件候选代码检查参数。"""

    preview_schema: str | dict[str, Any] | None = Field(default=None, description="与候选源码一同检查的 preview_schema。")
    component_type: WorkspaceComponentType | None = Field(default=None, description="候选组件分类。")


class PageCopyPayload(OperationArgumentsModel):
    """页面复制到目标项目的参数。"""

    target_project_id: int = Field(gt=0, description="目标项目 ID；必须与源页面处于同一工作空间。")
    title: str | None = Field(default=None, min_length=1, max_length=128, description="复制后页面标题；不传则沿用源页面。")
    summary: str | None = Field(default=None, max_length=500, description="复制后页面摘要。")
    route_placement: Literal["none", "root", "group"] = Field(default="none", description="是否同时把新页面放入目标项目路由树。")
    parent_route_id: int | None = Field(default=None, ge=1, description="route_placement=group 时的目标分组路由 ID。")
    route: str | None = Field(default=None, min_length=1, max_length=128, description="可选路由片段；不传时由平台生成。")


class AssetCopyPayload(OperationArgumentsModel):
    """复制资源参数。"""

    name: str | None = Field(default=None, description="新资源名称。")
    original_name: str | None = Field(default=None, description="新资源展示文件名。")
    description: str | None = Field(default=None, description="新资源说明。")
    tags: list[str] | str | None = Field(default=None, description="新资源标签。")
    status: RecordStatus = Field(default=RecordStatus.ACTIVE, description="新副本状态，通常使用 active。")
    archive_reason: str | None = Field(default=None, description="创建归档副本时的归档原因。")


class AssetPreviewContentPayload(OperationArgumentsModel):
    """资源内容差异预览参数。"""

    content: str = Field(description="拟写入的完整资源文本内容；该操作只生成差异，不落库。")


class AssetSaveUploadPayload(OperationArgumentsModel):
    """把会话上传图片保存为资源的参数。"""

    attachment_id: int = Field(gt=0, description="当前会话中用户上传图片的可信附件 ID。")
    name: str | None = Field(default=None, description="保存后的资源名称。")
    description: str | None = Field(default=None, description="资源用途说明。")
    tags: list[str] | str | None = Field(default=None, description="资源标签。")


class NamedCopyPayload(OperationArgumentsModel):
    """主题或样式复制参数。"""

    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="新副本 key；不传时由平台生成。")
    name: str | None = Field(default=None, min_length=1, max_length=128, description="新副本名称。")


class ReplaceRoutesPayload(OperationArgumentsModel):
    """项目路由树全量替换参数。"""

    routes: list[ProjectRouteItemWrite] = Field(description="完整的新路由树；未包含的现有节点会被移除。")
    change_note: str | None = Field(default=None, description="本次路由调整说明。")


class ReplaceStyleConfigPayload(OperationArgumentsModel):
    """项目 Markdown 样式规范全量替换参数。"""

    style_spec_markdown: str = Field(description="完整的新 Markdown 样式规范；传空字符串表示清空规范。")


class ThemeRenameKeyPayload(OperationArgumentsModel):
    """主题 key 重命名参数。"""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="新的主题 key；平台会同步当前工作空间内的引用方。")


QUERY_FILTER_MODELS: dict[tuple[str, str], type[OperationArgumentsModel]] = {
    ("project", "list"): CommonListFilters,
    ("project", "detail"): EmptyArguments,
    ("project", "route_tree"): EmptyArguments,
    ("project", "style_config"): ProjectStyleConfigFilters,
    ("page", "list"): PageListFilters,
    ("page", "detail"): EmptyArguments,
    ("page", "content"): EmptyArguments,
    ("component", "list"): ComponentListFilters,
    ("component", "detail"): EmptyArguments,
    ("component", "versions"): EmptyArguments,
    ("component", "dependencies"): EmptyArguments,
    ("asset", "list"): AssetListFilters,
    ("asset", "content"): EmptyArguments,
    ("asset", "tags"): EmptyArguments,
    ("theme", "list"): ArchivedListFilters,
    ("theme", "detail"): ArchivedDetailOptions,
    ("style", "list"): ArchivedListFilters,
    ("style", "detail"): ArchivedDetailOptions,
    ("runtime_kit", "list"): RuntimeKitListFilters,
    ("runtime_kit", "detail"): RuntimeKitDetailFilters,
    ("font", "list"): FontListFilters,
}


PAYLOAD_MODELS: dict[tuple[str, str, str | None], type[OperationArgumentsModel]] = {
    ("project", "create", None): ProjectCreatePayload,
    ("page", "create", None): PageCreatePayload,
    ("component", "create", None): ComponentCreatePayload,
    ("asset", "create", None): AssetCreatePayload,
    ("theme", "create", None): ThemeCreatePayload,
    ("style", "create", None): StyleCreatePayload,
    ("project", "update", None): ProjectUpdatePayload,
    ("page", "update", "metadata"): PageMetadataPayload,
    ("page", "update", "content"): PageContentPayload,
    ("component", "update", "metadata"): ComponentMetadataPayload,
    ("component", "update", "content"): ComponentContentPayload,
    ("asset", "update", "metadata"): AssetMetadataPayload,
    ("asset", "update", "content"): AssetContentPayload,
    ("theme", "update", None): ThemeUpdatePayload,
    ("style", "update", None): StyleUpdatePayload,
    ("component", "action", "publish"): ComponentPublishPayload,
    ("component", "action", "check"): ComponentCheckPayload,
    ("page", "action", "check"): PageCheckPayload,
    ("page", "action", "copy"): PageCopyPayload,
    ("asset", "action", "copy"): AssetCopyPayload,
    ("asset", "action", "preview_content"): AssetPreviewContentPayload,
    ("asset", "action", "save_upload"): AssetSaveUploadPayload,
    ("theme", "action", "copy"): NamedCopyPayload,
    ("style", "action", "copy"): NamedCopyPayload,
    ("project", "action", "replace_routes"): ReplaceRoutesPayload,
    ("project", "action", "replace_style_config"): ReplaceStyleConfigPayload,
    ("theme", "action", "rename_key"): ThemeRenameKeyPayload,
}


def get_query_filters_model(resource_type: str, action: str) -> type[OperationArgumentsModel] | None:
    """返回查询 action 对应的精确 filters 模型。"""

    return QUERY_FILTER_MODELS.get((resource_type, action))


def get_operation_payload_model(
    resource_type: str,
    operation: str,
    action: str | None,
) -> type[OperationArgumentsModel] | None:
    """返回写操作对应的精确 payload 模型；恢复动作共用 RestorePayload。"""

    if operation == "action" and action == "restore" and resource_type in {"page", "component", "asset", "theme", "style"}:
        return RestorePayload
    return PAYLOAD_MODELS.get((resource_type, operation, action))
