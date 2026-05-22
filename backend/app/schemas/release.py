"""文件功能：定义预览 artifact、入口描述与前后端交互协议。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


PreviewKind = Literal["project", "page", "component", "asset"]
PreviewEntryType = Literal["route", "module", "component_host", "asset_host"]
PreviewScopeType = Literal["project", "workspace_component", "runtime_kit_component", "workspace_asset"]
ComponentPreviewMode = Literal["saved", "draft"]
ComponentPreviewSource = Literal["workspace_component", "runtime_kit"]


class PreviewEntryDescriptor(BaseModel):
    """预览入口描述，用于区分项目路由、单页面模块和组件宿主页。"""

    entry_type: PreviewEntryType
    route: str | None = None
    module_path: str | None = None

    @model_validator(mode="after")
    def validate_descriptor(self) -> "PreviewEntryDescriptor":
        """校验不同入口类型所需的字段组合，避免歧义入口进入 Runtime。"""

        if self.entry_type == "route":
            if not str(self.route or "").strip():
                raise ValueError("entry_type=route 时必须提供 route。")
            self.module_path = None
            return self

        if self.entry_type == "module":
            if not str(self.module_path or "").strip():
                raise ValueError("entry_type=module 时必须提供 module_path。")
            self.route = None
            return self

        self.route = None
        self.module_path = None
        return self


class PreviewArtifactCreateRequest(BaseModel):
    """项目/页面预览 artifact 创建请求。"""

    entry_descriptor: PreviewEntryDescriptor | None = None


class PreviewArtifactResponse(BaseModel):
    """统一的预览 artifact 创建响应。"""

    preview_url: str
    artifact_id: str
    preview_kind: PreviewKind
    entry_descriptor: PreviewEntryDescriptor
    viewport_width: int
    viewport_height: int
    project_id: int | None = None
    workspace_id: int | None = None
    component_preview_mode: ComponentPreviewMode | None = None
    component_source: ComponentPreviewSource | None = None
    component_code: str | None = None
    component_version_no: int | None = None
    runtime_kit_component_name: str | None = None
    runtime_kit_manifest_version: str | None = None
    asset_id: int | None = None
    asset_name: str | None = None
