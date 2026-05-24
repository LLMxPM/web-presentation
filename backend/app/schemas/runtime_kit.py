"""文件功能：定义 Runtime Kit 内建能力目录和预览接口的请求与响应模型。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.component_preview_options import ComponentPreviewOptions
from app.schemas.common import SchemaBase


RuntimeKitComponentSource = Literal["runtime_kit"]
RuntimeKitCapabilityKind = Literal["component", "composable", "util", "type"]
RuntimeKitCapabilityAudience = Literal["backend", "agent"]


class RuntimeKitCapabilityItem(SchemaBase):
    """Runtime Kit 内建能力目录项。"""

    kind: RuntimeKitCapabilityKind
    base_name: str
    version_no: int
    name: str
    import_path: str
    category: str
    description: str
    display_name: str
    summary: str
    tags: list[str]
    previewable: bool
    preview_schema: dict[str, Any] | None = None
    preview_options: dict[str, Any] | None = None
    usage: list[str]
    returns: str | None = None
    return_example: list[str]
    constraints: list[str]
    audiences: list[RuntimeKitCapabilityAudience]
    manifest_version: str


class RuntimeKitCapabilityListResponse(BaseModel):
    """Runtime Kit 内建能力列表响应。"""

    items: list[RuntimeKitCapabilityItem]
    total: int
    manifest_version: str | None = None


class RuntimeKitComponentPreviewRequest(BaseModel):
    """创建 Runtime Kit 内建组件预览 artifact 的入参。"""

    workspace_id: int
    preview_options: ComponentPreviewOptions | None = None


class RuntimeKitComponentPreviewMeta(BaseModel):
    """Runtime Kit 内建组件预览元数据。"""

    component_source: RuntimeKitComponentSource = "runtime_kit"
    runtime_kit_component_name: str = Field(min_length=1)
    runtime_kit_manifest_version: str
