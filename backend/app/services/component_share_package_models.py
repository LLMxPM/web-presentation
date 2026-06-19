"""文件功能：定义组件分享包导入导出过程使用的数据结构与基础常量。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion


PACKAGE_SCHEMA_VERSION = 2
COMPONENT_IMPORT_PATTERN = re.compile(
    r"@workspace-components/(?P<component_code>[A-Za-z0-9_-]+)/v/(?P<version_no>\d+)(?:\.vue)?"
)


@dataclass(slots=True)
class ExportComponentSnapshot:
    """分享包导出过程中使用的组件发布版本快照。"""

    component: WorkspaceComponent
    version: WorkspaceComponentVersion
    dependencies: list[tuple[str, int]]
    asset_names: list[str]
    font_asset_names: list[str]
    missing_static_asset_names: list[str]
    dynamic_resource_component_names: list[str]


@dataclass(slots=True)
class ExportAssetCollection:
    """组件导出资源收集结果，区分自动、手动和 warning。"""

    assets: list[WorkspaceAsset]
    automatic_asset_names: list[str]
    manual_asset_names: list[str]
    missing_static_asset_names: list[str]
    missing_manual_asset_names: list[str]
    dynamic_resource_components: list[str]
    warnings: list[str]


@dataclass(slots=True)
class ExportPackagePlan:
    """组件分享包导出前的完整准备结果。"""

    root_components: list[WorkspaceComponent]
    snapshots: list[ExportComponentSnapshot]
    asset_collection: ExportAssetCollection
    font_configs: list[WorkspaceFontConfig]


@dataclass(slots=True)
class PackageComponent:
    """从分享包读取出的组件内容和元数据。"""

    source_component_code: str
    source_version_no: int
    metadata: dict[str, Any]
    content: str
    preview_schema: str | None
    dependencies: list[tuple[str, int]]
    asset_names: list[str]
    font_asset_names: list[str]
    content_hash: str | None = None
    preview_schema_hash: str | None = None
    component_fingerprint: str | None = None
    fingerprint_schema_version: int | None = None


@dataclass(slots=True)
class PackageAsset:
    """从分享包读取出的资源内容和元数据。"""

    metadata: dict[str, Any]
    content: bytes


@dataclass(slots=True)
class ParsedPackage:
    """已解析的组件分享包。"""

    manifest: dict[str, Any]
    components: list[PackageComponent]
    assets: list[PackageAsset]
    font_configs: list[dict[str, Any]]


@dataclass(slots=True)
class PackageComponentImportAction:
    """组件分享包预检和导入时的组件处理动作。"""

    package_component: PackageComponent
    action: str
    component_fingerprint: str | None
    matched_component: WorkspaceComponent | None
    match_reason: str | None


