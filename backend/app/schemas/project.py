"""文件功能：定义项目实体的请求与响应模型。"""

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import RecordStatus
from app.models.enums import AssetType
from app.schemas.common import SchemaBase
from app.schemas.presentation_style import ProjectCreateConfiguration, ProjectDefaultConfiguration, ProjectUpdateConfiguration
from app.schemas.project_app_config import ProjectMenuMode


_HTTP_URL_PATTERN = re.compile(r"^https?://", flags=re.IGNORECASE)
_PROJECT_BUILD_EXTRA_ASSET_NAMES_MAX_COUNT = 500
_PROJECT_BUILD_EXTRA_ASSET_NAME_MAX_LENGTH = 255
_PROJECT_SUGGESTED_REFERENCE_ASSET_MAX_COUNT = 100


class ProjectBuildExtraAssetsConfig(BaseModel):
    """项目级构建额外资源配置，供整包构建补充动态资源依赖。"""

    model_config = ConfigDict(extra="forbid")

    asset_names: list[str] = Field(
        default_factory=list,
        description="构建时额外打包的工作空间资源 name；不接受 URL，最多 500 项并按顺序去重。",
    )

    @field_validator("asset_names", mode="before")
    @classmethod
    def normalize_asset_names(cls, value: object) -> list[str]:
        """归一化资源名列表，保持顺序去重并拒绝 URL。"""

        return normalize_project_build_extra_asset_names(value)


def normalize_project_build_extra_assets_config(value: object | None) -> ProjectBuildExtraAssetsConfig:
    """将项目构建额外资源 JSON 统一转为受控配置对象。"""

    if value is None:
        return ProjectBuildExtraAssetsConfig()
    if isinstance(value, ProjectBuildExtraAssetsConfig):
        return value
    if isinstance(value, dict):
        return ProjectBuildExtraAssetsConfig.model_validate(value)
    raise ValueError("构建额外资源配置必须是 JSON 对象。")


def normalize_project_build_extra_asset_names(value: object) -> list[str]:
    """校验并归一化构建额外资源名列表。"""

    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("asset_names 必须是字符串数组。")
    if len(value) > _PROJECT_BUILD_EXTRA_ASSET_NAMES_MAX_COUNT:
        raise ValueError(f"asset_names 最多支持 {_PROJECT_BUILD_EXTRA_ASSET_NAMES_MAX_COUNT} 个资源名。")

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = str(item or "").strip().replace("\\", "/").lstrip("./")
        if not normalized:
            continue
        if len(normalized) > _PROJECT_BUILD_EXTRA_ASSET_NAME_MAX_LENGTH:
            raise ValueError(f"资源名长度不能超过 {_PROJECT_BUILD_EXTRA_ASSET_NAME_MAX_LENGTH} 个字符。")
        if _HTTP_URL_PATTERN.match(normalized):
            raise ValueError("构建额外资源名必须来自工作空间资源 name，不能是 URL。")
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


class ProjectCreateRequest(BaseModel):
    """创建项目入参，展示配置通过明确初始化来源生成。"""

    model_config = ConfigDict(extra="forbid")

    workspace_id: int
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus = RecordStatus.ACTIVE
    configuration: ProjectCreateConfiguration = Field(default_factory=ProjectDefaultConfiguration)
    build_extra_assets_json: ProjectBuildExtraAssetsConfig = Field(default_factory=ProjectBuildExtraAssetsConfig)

    @model_validator(mode="after")
    def normalize_build_extra_assets_json(self) -> "ProjectCreateRequest":
        """保证创建请求中的构建额外资源配置始终为受控对象。"""

        self.build_extra_assets_json = normalize_project_build_extra_assets_config(self.build_extra_assets_json)
        return self


class ProjectUpdateRequest(BaseModel):
    """更新项目入参，项目专属字段与共享样式配置明确分层。"""

    model_config = ConfigDict(extra="forbid")

    workspace_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus | None = None
    configuration: ProjectUpdateConfiguration | None = None
    build_extra_assets_json: ProjectBuildExtraAssetsConfig | None = None

    @model_validator(mode="after")
    def normalize_build_extra_assets_json(self) -> "ProjectUpdateRequest":
        """保证更新请求中的构建额外资源配置始终为受控对象。"""

        if self.build_extra_assets_json is not None:
            self.build_extra_assets_json = normalize_project_build_extra_assets_config(self.build_extra_assets_json)
        return self


class ProjectItem(SchemaBase):
    """项目响应模型，同时返回所属工作空间信息。"""

    id: int
    workspace_id: int
    workspace_name: str
    code: str
    name: str
    description: str | None
    is_system_managed: bool = False
    status: RecordStatus
    archived_at: datetime | None
    page_width: int
    page_height: int
    base_font_size: str
    icon_default_stroke_width: int
    show_pdf_export_button: bool
    menu_mode: ProjectMenuMode
    theme_key: str | None
    theme_config_yaml: str
    style_spec_markdown: str
    build_extra_assets_json: ProjectBuildExtraAssetsConfig
    first_page_title: str | None = None
    first_page_screenshot_url: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None
    updated_by: int | None


class ProjectSuggestedReferenceAssetItem(BaseModel):
    """项目建议引用资源摘要，避免向 AI 默认上下文暴露 URL 与标签。"""

    id: int
    name: str
    original_name: str
    description: str | None = None
    asset_type: AssetType
    content_editable: bool = False
    approx_aspect_ratio: str | None = None
    approx_aspect_ratio_value: float | None = None
    aspect_ratio_source: str | None = None


class ProjectSuggestedReferenceAssetsResponse(BaseModel):
    """项目建议引用资源列表响应。"""

    items: list[ProjectSuggestedReferenceAssetItem] = Field(default_factory=list)


class ProjectSuggestedReferenceAssetsUpdateRequest(BaseModel):
    """覆盖保存项目建议引用资源的请求体。"""

    asset_ids: list[int] = Field(default_factory=list, max_length=_PROJECT_SUGGESTED_REFERENCE_ASSET_MAX_COUNT)
