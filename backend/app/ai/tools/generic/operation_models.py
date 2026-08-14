"""文件功能：定义内容助手通用业务操作的精确参数模型，供操作手册与运行时校验共同复用。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.tools.shared import SourceEditInput
from app.models.enums import AssetType, WorkspaceComponentType
from app.schemas.project import ProjectBuildExtraAssetsConfig
from app.schemas.presentation_style import (
    ProjectCreateConfiguration,
    ProjectDefaultConfiguration,
    StyleConfiguration,
    StyleConfigurationPatch,
)
from app.schemas.project_route import ProjectRouteItemWrite
from app.schemas.theme import ThemePalette


class OperationArgumentsModel(BaseModel):
    """操作参数基础模型，拒绝手册未声明的额外字段。"""

    model_config = ConfigDict(extra="forbid")


class NonEmptyPatchModel(OperationArgumentsModel):
    """更新参数基础模型，拒绝没有任何显式字段的空补丁。"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    @model_validator(mode="after")
    def require_field(self) -> "NonEmptyPatchModel":
        """确保更新操作至少表达一项真实修改。"""

        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待修改字段。")
        return self


class EmptyArguments(OperationArgumentsModel):
    """不接受额外参数的操作。"""


class CommonListFilters(OperationArgumentsModel):
    """项目、主题和样式列表通用筛选参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始。")
    page_size: int = Field(default=50, ge=1, le=100, description="每页数量，最大 100。")
    keyword: str | None = Field(default=None, description="按名称或描述进行模糊搜索的关键词。")
    sort_by: str = Field(default="updated_at", description="排序字段，通常使用 updated_at。")
    sort_order: Literal["asc", "desc"] = Field(default="desc", description="排序方向。")


class PageListFilters(CommonListFilters):
    """页面列表筛选参数。"""

    project_id: int | None = Field(default=None, ge=1, description="可选项目 ID；必须属于当前工作空间和本轮项目工作集。")


class VersionContentOptions(OperationArgumentsModel):
    """页面或组件指定历史版本内容的定位参数。"""

    version_no: int = Field(ge=1, description="要读取的历史版本号。")


class ComponentListFilters(OperationArgumentsModel):
    """组件列表筛选参数。"""

    component_type: WorkspaceComponentType | None = Field(default=None, description="组件分类：页面组件（整页模板）、内容组件（页面内内容块）、原子组件（小粒度 UI 元素）。")
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
    configuration: ProjectCreateConfiguration = Field(default_factory=ProjectDefaultConfiguration, description="default/style/custom 三种初始化来源。")
    build_assets: ProjectBuildExtraAssetsConfig | None = Field(default=None, description="构建时需要额外打包的工作空间资源名称。")


class ProjectMetadataPayload(NonEmptyPatchModel):
    """修改项目名称与说明。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的项目名称。")
    description: str | None = Field(default=None, max_length=2000, description="新的项目说明。")


class ProjectConfigurationPayload(StyleConfigurationPatch):
    """部分更新项目展示配置和建议组件快照。"""


class ProjectApplyStylePayload(OperationArgumentsModel):
    """从工作空间样式完整覆盖项目样式快照。"""

    style_id: int = Field(gt=0, description="当前工作空间内 active 样式 ID。")


class ProjectBuildAssetsPayload(ProjectBuildExtraAssetsConfig):
    """修改项目构建时额外打包的资源名。"""


class PageCreatePayload(OperationArgumentsModel):
    """创建 Vue 页面参数。"""

    project_id: int = Field(gt=0, description="目标项目 ID；必须属于当前工作空间和本轮项目工作集。")
    title: str = Field(min_length=1, max_length=128, description="页面标题。")
    content: str = Field(min_length=1, description="完整、可编译的 Vue 单文件组件源码。")
    summary: str | None = Field(default=None, max_length=500, description="页面内容摘要。")
    speaker_notes: str | None = Field(default=None, max_length=10000, description="演讲者备注。")
    route_placement: Literal["none", "root", "group"] = Field(default="none", description="是否同时写入项目路由树。")
    parent_route_id: int | None = Field(default=None, ge=1, description="放入分组时的目标分组路由 ID。")
    route: str | None = Field(default=None, min_length=1, max_length=128, description="可选路由片段；不传时由平台生成。")

    @model_validator(mode="after")
    def validate_route_placement(self) -> "PageCreatePayload":
        """确保路由位置与父分组参数形成合法组合。"""

        _validate_route_placement(self.route_placement, self.parent_route_id)
        return self


class PageMetadataPayload(NonEmptyPatchModel):
    """页面元数据修改参数。"""

    title: str | None = Field(default=None, min_length=1, max_length=128, description="新的页面标题。")
    summary: str | None = Field(default=None, max_length=500, description="新的页面摘要；空字符串表示清空。")
    speaker_notes: str | None = Field(default=None, max_length=10000, description="新的演讲者备注；空字符串表示清空。")
    change_note: str | None = Field(default=None, max_length=255, description="本次修改说明。")

    @model_validator(mode="after")
    def require_metadata_field(self) -> "PageMetadataPayload":
        """修改说明不能单独构成页面元数据更新。"""

        if not self.model_fields_set.intersection({"title", "summary", "speaker_notes"}):
            raise ValueError("title、summary 与 speaker_notes 至少需要提供一项。")
        return self


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
    component_type: WorkspaceComponentType = Field(default=WorkspaceComponentType.CONTENT_COMPONENT, description="组件分类：页面组件（整页模板）、内容组件（页面内内容块）、原子组件（小粒度 UI 元素）。")
    summary: str | None = Field(default=None, max_length=500, description="组件职责和使用场景摘要。")
    preview_schema: str | dict[str, Any] = Field(
        description=(
            "必填的组件预览字段 Schema，可传 JSON 对象或等价 JSON 字符串；它描述字段而不是填写预览值。"
            "组件属性必须放在 props 下，并以字段名映射 type、default 等定义；内容组件的 props 还必须包含至少一个"
            " width、height、minHeight 或 aspectRatio 等尺寸控制字段。"
        )
    )
    change_note: str | None = Field(default=None, max_length=255, description="初始草稿说明。")


class ComponentMetadataPayload(NonEmptyPatchModel):
    """组件元数据修改参数。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的组件展示名称。")
    import_name: str | None = Field(default=None, min_length=1, max_length=128, description="新的 PascalCase 引用名。")
    component_type: WorkspaceComponentType | None = Field(default=None, description="新的组件分类：页面组件（整页模板）、内容组件（页面内内容块）、原子组件（小粒度 UI 元素）。")
    summary: str | None = Field(default=None, max_length=500, description="新的组件摘要。")
    preview_schema: str | dict[str, Any] | None = Field(
        default=None,
        description=(
            "新的组件预览字段 Schema；组件属性必须放在 props 下，并以字段名映射 type、default 等定义。"
            "所有组件都必须保留 preview_schema，内容组件还必须在 props 中声明尺寸控制字段。"
        ),
    )
    change_note: str | None = Field(default=None, max_length=255, description="本次修改说明。")

    @model_validator(mode="after")
    def require_metadata_field(self) -> "ComponentMetadataPayload":
        """修改说明不能单独构成组件元数据更新。"""

        if not self.model_fields_set.difference({"change_note"}):
            raise ValueError("至少需要提供一个组件元数据字段。")
        return self


class ComponentContentPayload(OperationArgumentsModel):
    """组件源码结构化修改参数。"""

    edits: list[SourceEditInput] = Field(min_length=1, description="按顺序应用的结构化源码编辑。")
    base_draft_hash: str = Field(min_length=1, description="读取组件详情时得到的当前草稿 SHA-256 指纹。")
    base_published_version_no: int = Field(ge=0, description="读取组件详情时得到的草稿基线发布版本号。")
    change_note: str | None = Field(default=None, max_length=255, description="本次源码修改说明。")


EditableAssetType = Literal["icon", "image", "drawio", "mermaid", "chart", "formula"]


class AssetCreatePayload(OperationArgumentsModel):
    """创建可编辑文本资源参数。"""

    asset_type: EditableAssetType = Field(
        description=(
            "可创建的资源类型。icon 表示 SVG 图标，image 仅表示 SVG 图片，不存在独立的 svg 类型；"
            "不支持非 SVG 位图、video 或 font。"
        )
    )
    name: str = Field(
        min_length=1,
        max_length=255,
        description="工作空间内唯一的稳定引用名称；不能包含 / 或 \\，创建后页面和组件通过该名称引用资源。",
    )
    original_name: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "带扩展名的展示文件名：icon 和 SVG image 使用 .svg；drawio 使用 .drawio/.xml；"
            "mermaid 使用 .mmd/.mermaid/.txt；chart 使用 .json/.yaml/.yml；formula 使用 .tex/.txt。"
        ),
    )
    content: str = Field(
        min_length=1,
        description=(
            "完整 UTF-8 文本内容，规范化后不能为空且不得超过 512 KiB。SVG/Draw.io 必须是可解析 XML；"
            "Chart 必须是可解析的 JSON/YAML 且顶层为对象；Mermaid 和 Formula 保存源码文本。"
        ),
    )
    description: str | None = Field(default=None, description="资源用途说明。")
    tags: list[str] | str | None = Field(default=None, description="标签数组，或兼容的逗号分隔字符串。")
    approx_aspect_ratio: str | None = Field(
        default=None,
        description="可选的正数近似宽高比，支持 16:9、4/3 或 1.5；省略时由可解析内容自动推导（若支持）。",
    )


class AssetMetadataPayload(NonEmptyPatchModel):
    """资源元数据修改参数。"""

    name: str | None = Field(default=None, min_length=1, description="新的稳定资源名。")
    original_name: str | None = Field(default=None, min_length=1, description="新的展示文件名。")
    description: str | None = Field(default=None, description="新的资源说明。")
    tags: list[str] | str | None = Field(default=None, description="替换后的标签。")
    approx_aspect_ratio: str | None = Field(default=None, description="新的近似宽高比。")
    clear_approx_aspect_ratio: bool = Field(default=False, description="是否明确清除已有近似宽高比；与 approx_aspect_ratio 不要同时使用。")

    @model_validator(mode="after")
    def validate_aspect_ratio_operation(self) -> "AssetMetadataPayload":
        """拒绝同时设置和清除近似宽高比。"""

        if self.approx_aspect_ratio is not None and self.clear_approx_aspect_ratio:
            raise ValueError("approx_aspect_ratio 与 clear_approx_aspect_ratio=true 不能同时提交。")
        if self.model_fields_set == {"clear_approx_aspect_ratio"} and not self.clear_approx_aspect_ratio:
            raise ValueError("clear_approx_aspect_ratio=false 不构成有效更新。")
        return self


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


class ThemeUpdatePayload(NonEmptyPatchModel):
    """限制内容助手修改主题时不能接触 Logo 和字体字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的主题名称。")
    description: str | None = Field(default=None, max_length=2000, description="新的主题说明。")
    palette: ThemePalette | None = Field(default=None, description="完整替换后的主题色板。")


class StyleCreatePayload(OperationArgumentsModel):
    """创建工作空间样式模板参数。"""

    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="样式稳定 key。")
    name: str = Field(min_length=1, max_length=128, description="样式展示名称。")
    description: str | None = Field(default=None, max_length=2000, description="样式用途说明。")
    configuration: StyleConfiguration = Field(default_factory=StyleConfiguration, description="完整展示配置和建议组件。")


class StyleMetadataPayload(NonEmptyPatchModel):
    """修改工作空间样式名称与说明。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="新的样式名称。")
    description: str | None = Field(default=None, max_length=2000, description="新的样式说明。")


class StyleConfigurationPayload(StyleConfigurationPatch):
    """部分更新工作空间样式配置与建议组件。"""


class ComponentPublishPayload(OperationArgumentsModel):
    """发布组件草稿参数。"""

    release_name: str | None = Field(default=None, description="可选发布版本名称。")
    change_note: str | None = Field(default=None, description="发布说明。")


class ValidationSourcePayload(OperationArgumentsModel):
    """页面或组件校验候选来源，确保完整源码与 edits 不混用。"""

    mode: Literal["current", "content", "edits"] = Field(description="校验当前内容、完整候选源码或结构化 edits。")
    content: str | None = Field(default=None, min_length=1, description="mode=content 时的完整候选源码。")
    edits: list[SourceEditInput] | None = Field(default=None, min_length=1, description="mode=edits 时应用到目标当前源码的编辑。")

    @model_validator(mode="after")
    def validate_source(self) -> "ValidationSourcePayload":
        """按 mode 约束候选内容字段。"""

        if self.mode == "current" and (self.content is not None or self.edits is not None):
            raise ValueError("mode=current 时不能提交 content 或 edits。")
        if self.mode == "content" and (self.content is None or self.edits is not None):
            raise ValueError("mode=content 时必须且只能提交 content。")
        if self.mode == "edits" and (self.edits is None or self.content is not None):
            raise ValueError("mode=edits 时必须且只能提交 edits。")
        return self


class PageCheckPayload(ValidationSourcePayload):
    """页面候选代码检查参数。"""

    project_id: int | None = Field(default=None, ge=1, description="无页面目标时，完整页面源码校验使用的明确项目 ID。")


class ComponentCheckPayload(ValidationSourcePayload):
    """组件候选代码检查参数。"""

    preview_schema: str | dict[str, Any] | None = Field(default=None, description="与候选源码一同检查的 preview_schema。")
    component_type: WorkspaceComponentType | None = Field(default=None, description="候选组件分类：页面组件（整页模板）、内容组件（页面内内容块）、原子组件（小粒度 UI 元素）。")


class PageCopyPayload(OperationArgumentsModel):
    """页面复制到目标项目的参数，支持在源项目内创建副本。"""

    source_id: int = Field(gt=0, description="源页面 ID。")
    project_id: int = Field(gt=0, description="目标项目 ID；必须与源页面处于同一工作空间，可以是源页面所属项目。")
    title: str | None = Field(default=None, min_length=1, max_length=128, description="复制后页面标题；不传则沿用源页面。")
    summary: str | None = Field(default=None, max_length=500, description="复制后页面摘要。")
    route_placement: Literal["none", "root", "group"] = Field(default="none", description="是否同时把新页面放入目标项目路由树。")
    parent_route_id: int | None = Field(default=None, ge=1, description="route_placement=group 时的目标分组路由 ID。")
    route: str | None = Field(default=None, min_length=1, max_length=128, description="可选路由片段；不传时由平台生成。")

    @model_validator(mode="after")
    def validate_route_placement(self) -> "PageCopyPayload":
        """确保复制后的路由位置参数完整且无歧义。"""

        _validate_route_placement(self.route_placement, self.parent_route_id)
        return self


class AssetCopyPayload(OperationArgumentsModel):
    """复制资源参数。"""

    source_id: int = Field(gt=0, description="源资源 ID。")
    name: str | None = Field(default=None, description="新资源名称。")
    original_name: str | None = Field(default=None, description="新资源展示文件名。")
    description: str | None = Field(default=None, description="新资源说明。")
    tags: list[str] | str | None = Field(default=None, description="新资源标签。")


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

    source_id: int = Field(gt=0, description="源主题或样式 ID。")
    key: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$", description="新副本 key；不传时由平台生成。")
    name: str | None = Field(default=None, min_length=1, max_length=128, description="新副本名称。")


class ReplaceRoutesPayload(OperationArgumentsModel):
    """项目路由树全量替换参数。"""

    routes: list[ProjectRouteItemWrite] = Field(description="完整的新路由树；未包含的现有节点会被移除。")
    change_note: str | None = Field(default=None, description="本次路由调整说明。")


def _validate_route_placement(route_placement: str, parent_route_id: int | None) -> None:
    """校验页面创建或复制的路由位置条件字段。"""

    if route_placement == "group" and parent_route_id is None:
        raise ValueError("route_placement=group 时必须提供 parent_route_id。")
    if route_placement != "group" and parent_route_id is not None:
        raise ValueError("只有 route_placement=group 时才能提供 parent_route_id。")


QUERY_FILTER_MODELS: dict[tuple[str, str], type[OperationArgumentsModel]] = {
    ("project", "list"): CommonListFilters,
    ("project", "detail"): EmptyArguments,
    ("project", "route_tree"): EmptyArguments,
    ("project", "configuration"): EmptyArguments,
    ("page", "list"): PageListFilters,
    ("page", "detail"): EmptyArguments,
    ("page", "content"): EmptyArguments,
    ("page", "versions"): EmptyArguments,
    ("page", "version_content"): VersionContentOptions,
    ("page", "dependencies"): EmptyArguments,
    ("component", "list"): ComponentListFilters,
    ("component", "detail"): EmptyArguments,
    ("component", "versions"): EmptyArguments,
    ("component", "version_content"): VersionContentOptions,
    ("component", "dependencies"): EmptyArguments,
    ("asset", "list"): AssetListFilters,
    ("asset", "detail"): EmptyArguments,
    ("asset", "content"): EmptyArguments,
    ("asset", "tags"): EmptyArguments,
    ("theme", "list"): CommonListFilters,
    ("theme", "detail"): EmptyArguments,
    ("style", "list"): CommonListFilters,
    ("style", "detail"): EmptyArguments,
    ("style", "configuration"): EmptyArguments,
    ("runtime_kit", "list"): RuntimeKitListFilters,
    ("runtime_kit", "detail"): RuntimeKitDetailFilters,
    ("font", "list"): FontListFilters,
}


PAYLOAD_MODELS: dict[tuple[str, str, str | None], type[OperationArgumentsModel]] = {
    ("project", "create", "new"): ProjectCreatePayload,
    ("page", "create", "new"): PageCreatePayload,
    ("page", "create", "copy"): PageCopyPayload,
    ("component", "create", "new"): ComponentCreatePayload,
    ("asset", "create", "new"): AssetCreatePayload,
    ("asset", "create", "copy"): AssetCopyPayload,
    ("asset", "create", "upload"): AssetSaveUploadPayload,
    ("theme", "create", "new"): ThemeCreatePayload,
    ("theme", "create", "copy"): NamedCopyPayload,
    ("style", "create", "new"): StyleCreatePayload,
    ("style", "create", "copy"): NamedCopyPayload,
    ("project", "update", "metadata"): ProjectMetadataPayload,
    ("project", "update", "configuration"): ProjectConfigurationPayload,
    ("project", "update", "apply_style"): ProjectApplyStylePayload,
    ("project", "update", "route_tree"): ReplaceRoutesPayload,
    ("project", "update", "build_assets"): ProjectBuildAssetsPayload,
    ("page", "update", "metadata"): PageMetadataPayload,
    ("page", "update", "content"): PageContentPayload,
    ("component", "update", "metadata"): ComponentMetadataPayload,
    ("component", "update", "content"): ComponentContentPayload,
    ("asset", "update", "metadata"): AssetMetadataPayload,
    ("asset", "update", "content"): AssetContentPayload,
    ("theme", "update", "metadata"): ThemeUpdatePayload,
    ("style", "update", "metadata"): StyleMetadataPayload,
    ("style", "update", "configuration"): StyleConfigurationPayload,
    ("component", "action", "publish"): ComponentPublishPayload,
    ("page", "validate", "check"): PageCheckPayload,
    ("component", "validate", "check"): ComponentCheckPayload,
    ("asset", "validate", "preview"): AssetPreviewContentPayload,
}


def get_query_filters_model(resource_type: str, action: str) -> type[OperationArgumentsModel] | None:
    """返回查询 action 对应的精确 filters 模型。"""

    return QUERY_FILTER_MODELS.get((resource_type, action))


def get_operation_payload_model(
    resource_type: str,
    operation: str,
    action: str | None,
) -> type[OperationArgumentsModel] | None:
    """返回写操作对应的精确 payload 模型。"""

    return PAYLOAD_MODELS.get((resource_type, operation, action))
