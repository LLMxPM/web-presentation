"""文件功能：定义项目整包构建任务的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import SchemaBase

ProjectBuildStatus = Literal["pending", "running", "succeeded", "failed"]


class ProjectBuildCreateRequest(BaseModel):
    """创建项目整包构建任务的请求。"""

    base_url: str = Field(default="./", min_length=1, max_length=255)


class ProjectBuildJobResponse(SchemaBase):
    """项目整包构建任务响应。"""

    id: int
    project_id: int
    snapshot_release_id: int
    base_url: str
    status: ProjectBuildStatus
    error_message: str | None
    artifact_storage_key: str | None
    artifact_download_url: str | None
    artifact_proxy_url: str | None = None
    artifact_entry_file: str | None
    artifact_sha256: str | None
    artifact_size_bytes: int | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ProjectBuildAssetSummary(BaseModel):
    """项目当前构建资源引用摘要，用于前端区分自动包含资源和额外资源。"""

    automatic_asset_names: list[str] = Field(default_factory=list)
    extra_asset_names: list[str] = Field(default_factory=list)
    included_asset_names: list[str] = Field(default_factory=list)
    dynamic_module_paths: list[str] = Field(default_factory=list)


class RuntimeBuildDispatchRequest(BaseModel):
    """Backend 派发给 Runtime 的整项目构建请求。"""

    artifact_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1, max_length=255)
