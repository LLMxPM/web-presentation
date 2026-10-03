"""文件功能：定义外部完整页面源码与组件草稿编辑基线的类型化响应。"""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import WorkspaceComponentType


class ExternalContentModel(BaseModel):
    """外部内容响应只返回公开契约字段。"""

    model_config = ConfigDict(extra="forbid")


class ExternalPageSourceResponse(ExternalContentModel):
    """页面完整源码与后续 edits 所需版本基线，不截断内容。"""

    page_id: int
    page_code: str
    version_no: int = Field(description="当前源码对应版本，可作为 base_version_no")
    source_code: str = Field(description="完整 Vue 源码")


class ExternalComponentDraftResponse(ExternalContentModel):
    """组件完整草稿与乐观并发基线，不使用发布源码冒充草稿。"""

    component_id: int
    import_name: str
    component_type: WorkspaceComponentType
    content: str = Field(description="完整可编辑草稿源码")
    preview_schema: str | None
    current_version_no: int = Field(description="当前发布版本，作为编辑 base_version_no")
    draft_base_version_no: int = Field(description="草稿基于的发布版本")
    draft_hash: str = Field(description="草稿 SHA-256，作为编辑 base_draft_hash")
