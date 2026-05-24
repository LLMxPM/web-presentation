"""文件功能：构建和导入工作空间组件离线分享包，封装 Zip、资源、字体与组件依赖处理。"""

from __future__ import annotations

import io
import json
import posixpath
import re
import zipfile
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.code_generator import (
    DEFAULT_CODE_RETRY_LIMIT,
    generate_code,
    is_code_unique_integrity_error,
)
from app.core.component_preview_schema import validate_component_preview_schema_text
from app.core.exceptions import AppException
from app.core.runtime_module_policy import load_runtime_kit_manifest
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, PageFileType, RecordStatus, WorkspaceComponentType
from app.models.font import WorkspaceFontConfig
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.module_dependency_repository import DEPENDENCY_KIND_COMPONENT, ModuleDependencyRepository
from app.repositories.component_resource_index_repository import ComponentResourceIndexRepository
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.schemas.component import (
    COMPONENT_IMPORT_NAME_PATTERN,
    ComponentShareImportResult,
    ComponentShareImportValidationResult,
    ComponentSharePackageAssetSummary,
    ComponentSharePackageComponentSummary,
    ComponentSharePackageFontSummary,
)
from app.services.asset_service import AssetService
from app.services.component_resource_index_service import ComponentResourceIndexService
from app.services.resource_reference_parser import DYNAMIC_RESOURCE_NAME
from app.services.workspace_component_service import CODE_PREFIX_COMPONENT, WorkspaceComponentService
from app.services.workspace_component_version_service import WorkspaceComponentVersionService
from app.services.workspace_font_service import WorkspaceFontService

PACKAGE_SCHEMA_VERSION = 1
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


class ComponentSharePackageService:
    """组件离线分享包服务，负责导出、预检和导入。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)
        self.module_dependency_repository = ModuleDependencyRepository(session)
        self.component_resource_index_repository = ComponentResourceIndexRepository(session)
        self.asset_service = AssetService(session)
        self.component_service = WorkspaceComponentService(session)
        self.component_version_service = WorkspaceComponentVersionService(session)

    async def export_package(self, *, workspace_id: int, component_ids: list[int]) -> tuple[bytes, str]:
        """按组件 ID 导出离线分享包，返回 Zip 内容与下载文件名。"""

        if not await self.component_repository.workspace_exists(workspace_id):
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")

        root_components = await self._load_root_components(workspace_id, component_ids)
        snapshots = await self._build_export_component_closure(root_components)
        assets = await self._collect_export_assets(workspace_id, snapshots)
        font_configs = await self._collect_export_font_configs(workspace_id, snapshots)
        archive_content = await self._build_zip_archive(
            workspace_id=workspace_id,
            root_components=root_components,
            snapshots=snapshots,
            assets=assets,
            font_configs=font_configs,
        )
        filename = self._build_export_filename(root_components)
        return archive_content, filename

    async def validate_import_package(self, *, workspace_id: int, archive_content: bytes) -> ComponentShareImportValidationResult:
        """预检组件分享包，不写入任何数据库记录。"""

        parsed = self._parse_package(archive_content)
        return await self._validate_parsed_package(workspace_id, parsed)

    async def import_package(self, *, workspace_id: int, archive_content: bytes, operator_id: int) -> ComponentShareImportResult:
        """正式导入组件分享包，创建资源、字体配置和组件发布版本。"""

        parsed = self._parse_package(archive_content)
        validation = await self._validate_parsed_package(workspace_id, parsed)
        if not validation.valid:
            raise AppException(
                status_code=400,
                code="COMPONENT_SHARE_PACKAGE_INVALID",
                detail="组件分享包预检未通过：" + "；".join(validation.errors),
            )

        last_error: IntegrityError | None = None
        for _ in range(DEFAULT_CODE_RETRY_LIMIT):
            try:
                await self._import_assets(workspace_id, parsed.assets)
                await self._import_font_configs(workspace_id, parsed.font_configs)
                imported_components = await self._import_components(workspace_id, parsed.components, operator_id)
                imported_component_items = [
                    await self.component_service._to_item(component)
                    for component in imported_components
                ]
                await self.session.commit()
                return ComponentShareImportResult(
                    imported_components=imported_component_items,
                    assets=validation.assets,
                    fonts=validation.fonts,
                )
            except IntegrityError as error:
                await self.session.rollback()
                if not is_code_unique_integrity_error(error, WorkspaceComponent):
                    raise
                last_error = error

        raise AppException(
            status_code=409,
            code="CODE_GENERATION_CONFLICT",
            detail="业务编码生成遇到并发冲突，请稍后重试。",
        ) from last_error

    async def _load_root_components(self, workspace_id: int, component_ids: list[int]) -> list[WorkspaceComponent]:
        """读取并校验导出根组件。"""

        unique_ids = list(dict.fromkeys(int(item) for item in component_ids))
        components: list[WorkspaceComponent] = []
        for component_id in unique_ids:
            component = await self.component_repository.get_by_id(component_id)
            if component is None or component.workspace_id != workspace_id:
                raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail=f"组件 {component_id} 不存在。")
            if component.current_version_no <= 0:
                raise AppException(
                    status_code=400,
                    code="COMPONENT_NOT_PUBLISHED",
                    detail=f'组件 "{component.name}" 尚未发布，不能导出分享包。',
                )
            components.append(component)
        return components

    async def _build_export_component_closure(
        self,
        root_components: list[WorkspaceComponent],
    ) -> list[ExportComponentSnapshot]:
        """按依赖优先顺序收集组件发布版本闭包。"""

        snapshots_by_version_id: dict[int, ExportComponentSnapshot] = {}
        visiting: set[int] = set()
        ordered: list[ExportComponentSnapshot] = []

        async def visit(component: WorkspaceComponent, version_no: int) -> None:
            version = await self.component_version_repository.get_by_component_and_version(component.id, version_no)
            if version is None:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_VERSION_NOT_FOUND",
                    detail=f'组件 "{component.name}" 的 v{version_no} 发布版本不存在。',
                )
            if version.id in snapshots_by_version_id:
                return
            if version.id in visiting:
                raise AppException(status_code=409, code="COMPONENT_DEPENDENCY_CYCLE_DETECTED", detail="组件依赖存在循环。")

            visiting.add(version.id)
            dependency_items = await self.module_dependency_repository.list_component_version_dependencies(version.id)
            dependencies: list[tuple[str, int]] = []
            for item in dependency_items:
                if item.dependency_kind != DEPENDENCY_KIND_COMPONENT:
                    continue
                if item.dependency_component_id is None or item.dependency_component_version_no is None:
                    raise AppException(status_code=409, code="COMPONENT_DEPENDENCY_INVALID", detail="组件依赖索引不完整。")
                dependency_component = await self.component_repository.get_by_id(item.dependency_component_id)
                if dependency_component is None:
                    raise AppException(status_code=409, code="COMPONENT_DEPENDENCY_MISSING", detail="组件依赖不存在。")
                dependencies.append((dependency_component.code, int(item.dependency_component_version_no)))
                await visit(dependency_component, int(item.dependency_component_version_no))

            for component_code, schema_version_no in self._collect_component_refs_from_text(version.preview_schema or ""):
                if (component_code, schema_version_no) in dependencies:
                    continue
                dependency_component = await self.component_repository.get_by_code(component_code)
                if dependency_component is None or dependency_component.workspace_id != component.workspace_id:
                    raise AppException(
                        status_code=409,
                        code="COMPONENT_PREVIEW_SCHEMA_DEPENDENCY_MISSING",
                        detail=f"组件 {component.code} 的 preview_schema 依赖组件不存在：{component_code} v{schema_version_no}。",
                    )
                dependencies.append((component_code, schema_version_no))
                await visit(dependency_component, schema_version_no)

            snapshot = ExportComponentSnapshot(
                component=component,
                version=version,
                dependencies=dependencies,
                asset_names=[],
                font_asset_names=WorkspaceFontService.collect_declared_font_asset_names([version.content]),
            )
            snapshots_by_version_id[version.id] = snapshot
            ordered.append(snapshot)
            visiting.remove(version.id)

        for component in root_components:
            await visit(component, component.current_version_no)

        return ordered

    async def _collect_export_assets(
        self,
        workspace_id: int,
        snapshots: list[ExportComponentSnapshot],
    ) -> list[WorkspaceAsset]:
        """收集组件源码和预览 schema 中引用的 active 普通资源。"""

        all_assets = await self._list_exportable_assets(workspace_id)
        asset_by_name = {asset.name: asset for asset in all_assets}
        missing_by_component: dict[str, list[str]] = {}
        dynamic_components: list[str] = []
        for snapshot in snapshots:
            asset_names, has_dynamic = await self._collect_snapshot_asset_names(snapshot)
            if has_dynamic:
                dynamic_components.append(snapshot.component.name)
            snapshot.asset_names = asset_names
            missing_names = [name for name in asset_names if name not in asset_by_name]
            if missing_names:
                missing_by_component[snapshot.component.name] = missing_names

        if dynamic_components:
            raise AppException(
                status_code=409,
                code="COMPONENT_SHARE_DYNAMIC_ASSET_REFERENCE",
                detail=(
                    "组件存在动态资源引用，离线包无法确定需要导出的资源，请改成静态资源名："
                    + "、".join(dynamic_components)
                    + "。"
                ),
            )

        required_names = sorted({
            *[name for snapshot in snapshots for name in snapshot.asset_names],
            *[name for snapshot in snapshots for name in snapshot.font_asset_names],
        })
        missing = [name for name in required_names if name not in asset_by_name]
        if missing_by_component or missing:
            missing_detail = "；".join(
                f'{component_name}：{", ".join(names)}'
                for component_name, names in sorted(missing_by_component.items())
            )
            if not missing_detail:
                missing_detail = ", ".join(missing)
            raise AppException(
                status_code=409,
                code="COMPONENT_SHARE_ASSET_MISSING",
                detail=f"组件引用的资源不存在或不可导出：{missing_detail}。",
            )

        selected_assets = [asset_by_name[name] for name in required_names]
        self._assert_unique_asset_hash_metadata(selected_assets)
        return selected_assets

    async def _collect_snapshot_asset_names(self, snapshot: ExportComponentSnapshot) -> tuple[list[str], bool]:
        """从组件版本资源索引读取资源名，旧版本无索引时使用内存解析回退。"""

        indexed_items = await self.component_resource_index_repository.list_component_resources_by_version(snapshot.version.id)
        if indexed_items:
            names = [item.resource_name for item in indexed_items]
        else:
            names = [
                resource_name
                for _, resource_name in ComponentResourceIndexService.collect_version_resource_items(
                    content=snapshot.version.content,
                    preview_schema=snapshot.version.preview_schema,
                )
            ]
        has_dynamic = DYNAMIC_RESOURCE_NAME in names
        static_names = sorted({name for name in names if name and name != DYNAMIC_RESOURCE_NAME})
        return static_names, has_dynamic

    async def _collect_export_font_configs(
        self,
        workspace_id: int,
        snapshots: list[ExportComponentSnapshot],
    ) -> list[WorkspaceFontConfig]:
        """收集组件显式声明的字体配置。"""

        font_names = sorted({name for snapshot in snapshots for name in snapshot.font_asset_names})
        if not font_names:
            return []
        result = await self.session.scalars(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_name.in_(font_names))
            .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
        )
        font_configs = list(result.all())
        found_names = {item.asset_name for item in font_configs}
        missing = [name for name in font_names if name not in found_names]
        if missing:
            raise AppException(
                status_code=409,
                code="COMPONENT_SHARE_FONT_CONFIG_MISSING",
                detail=f"组件声明的字体资源未注册或未启用：{', '.join(missing)}。",
            )
        return font_configs

    async def _build_zip_archive(
        self,
        *,
        workspace_id: int,
        root_components: list[WorkspaceComponent],
        snapshots: list[ExportComponentSnapshot],
        assets: list[WorkspaceAsset],
        font_configs: list[WorkspaceFontConfig],
    ) -> bytes:
        """按标准目录结构生成组件分享包 Zip。"""

        buffer = io.BytesIO()
        runtime_manifest_version = str(load_runtime_kit_manifest().get("version") or "")
        component_entries = [self._build_component_manifest_entry(snapshot) for snapshot in snapshots]
        asset_entries = [self._build_asset_manifest_entry(asset) for asset in assets]
        font_entries = [self._build_font_config_payload(item) for item in font_configs]
        manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "exported_at": utc_now().isoformat(),
            "runtime_kit_manifest_version": runtime_manifest_version,
            "root_components": [component.code for component in root_components],
            "components": component_entries,
            "assets": asset_entries,
            "fonts": font_entries,
        }

        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", self._dump_json(manifest))
            for snapshot in snapshots:
                base_path = f"components/{snapshot.component.code}"
                archive.writestr(f"{base_path}/component.json", self._dump_json(self._build_component_payload(snapshot)))
                archive.writestr(f"{base_path}/index.vue", normalize_text_to_lf(snapshot.version.content))
                archive.writestr(f"{base_path}/preview.schema.json", snapshot.version.preview_schema or "{}")

            for asset in assets:
                asset_base_path = f"assets/{asset.file_hash}"
                archive.writestr(f"{asset_base_path}/asset.json", self._dump_json(self._build_asset_payload(asset)))
                archive.writestr(
                    f"{asset_base_path}/{self._safe_archive_filename(asset.original_name)}",
                    await self.asset_service.driver.read_content(workspace_id, asset.file_name),
                )
            archive.writestr("fonts/font-configs.json", self._dump_json(font_entries))
        return buffer.getvalue()

    def _parse_package(self, archive_content: bytes) -> ParsedPackage:
        """从 Zip 二进制内容解析分享包结构。"""

        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_content))
        except zipfile.BadZipFile as error:
            raise AppException(status_code=400, code="COMPONENT_SHARE_PACKAGE_INVALID", detail="上传文件不是合法 Zip。") from error

        with archive:
            names = {self._normalize_zip_name(item.filename) for item in archive.infolist() if not item.is_dir()}
            if "manifest.json" not in names:
                raise AppException(status_code=400, code="COMPONENT_SHARE_MANIFEST_MISSING", detail="分享包缺少 manifest.json。")

            manifest = self._read_json(archive, "manifest.json")
            if not isinstance(manifest, dict):
                raise AppException(status_code=400, code="COMPONENT_SHARE_MANIFEST_INVALID", detail="manifest.json 必须是 JSON 对象。")
            component_codes = self._resolve_package_component_codes(manifest, names)
            components = [
                self._read_package_component(archive, component_code)
                for component_code in component_codes
            ]
            asset_hashes = self._resolve_package_asset_hashes(manifest, names)
            assets = [
                self._read_package_asset(archive, asset_hash)
                for asset_hash in asset_hashes
            ]
            font_configs_raw = self._read_json(archive, "fonts/font-configs.json") if "fonts/font-configs.json" in names else []
            font_configs = font_configs_raw
            if not isinstance(font_configs, list):
                raise AppException(status_code=400, code="COMPONENT_SHARE_FONT_CONFIG_INVALID", detail="fonts/font-configs.json 必须是数组。")
            if any(not isinstance(item, dict) for item in font_configs):
                raise AppException(status_code=400, code="COMPONENT_SHARE_FONT_CONFIG_INVALID", detail="fonts/font-configs.json 的每一项必须是对象。")
            return ParsedPackage(
                manifest=manifest,
                components=components,
                assets=assets,
                font_configs=font_configs,
            )

    async def _validate_parsed_package(
        self,
        workspace_id: int,
        parsed: ParsedPackage,
    ) -> ComponentShareImportValidationResult:
        """校验分享包内容并返回可展示的预检摘要。"""

        errors: list[str] = []
        schema_version = self._coerce_int(parsed.manifest.get("schema_version"))
        runtime_version = str(parsed.manifest.get("runtime_kit_manifest_version") or "").strip()
        if schema_version != PACKAGE_SCHEMA_VERSION:
            errors.append(f"分享包 schema_version 必须是 {PACKAGE_SCHEMA_VERSION}。")
        if not await self.component_repository.workspace_exists(workspace_id):
            errors.append("目标工作空间不存在。")

        component_summaries = self._build_component_summaries(parsed.components, errors)
        asset_summaries = await self._build_asset_summaries(workspace_id, parsed.assets, errors)
        font_summaries = await self._build_font_summaries(workspace_id, parsed.font_configs, errors)
        await self._validate_component_imports(workspace_id, parsed.components, errors)
        self._validate_package_dependency_closure(parsed.components, errors)
        self._validate_package_font_assets(parsed, errors)

        return ComponentShareImportValidationResult(
            valid=not errors,
            schema_version=schema_version,
            runtime_kit_manifest_version=runtime_version or None,
            components=component_summaries,
            assets=asset_summaries,
            fonts=font_summaries,
            errors=errors,
        )

    async def _import_assets(self, workspace_id: int, package_assets: list[PackageAsset]) -> None:
        """导入或复用包内资源。"""

        for package_asset in package_assets:
            metadata = package_asset.metadata
            name = str(metadata["name"]).strip()
            existing = await self._get_asset_by_name(workspace_id, name)
            if existing is not None:
                continue
            asset_type = AssetType(str(metadata["asset_type"]))
            content = package_asset.content
            file_hash = hashlib.sha256(content).hexdigest()
            original_name = self._safe_archive_filename(str(metadata["original_name"]))
            AssetService._validate_asset_file_type(asset_type, original_name, metadata.get("content_type"))
            AssetService._validate_uploaded_asset_content(asset_type, original_name, content)
            ext = "".join(Path(original_name).suffixes)
            save_name = await self.asset_service.driver.upload(
                workspace_id,
                file_hash,
                ext,
                content,
                str(metadata.get("content_type") or "") or None,
            )
            self.session.add(
                WorkspaceAsset(
                    workspace_id=workspace_id,
                    name=name,
                    file_name=save_name,
                    original_name=original_name,
                    description=metadata.get("description"),
                    file_size=len(content),
                    file_hash=file_hash,
                    content_type=metadata.get("content_type"),
                    asset_type=asset_type.value,
                    tags=list(metadata.get("tags") or []),
                    analysis_metadata=metadata.get("render_metadata"),
                    render_metadata=metadata.get("render_metadata"),
                    status=RecordStatus.ACTIVE.value,
                )
            )
        await self.session.flush()

    async def _import_font_configs(self, workspace_id: int, font_configs: list[dict[str, Any]]) -> None:
        """导入或复用包内字体配置。"""

        for item in font_configs:
            asset_name = str(item["asset_name"]).strip()
            existing = await self._get_font_config_by_asset_name(workspace_id, asset_name)
            if existing is not None:
                continue
            asset = await self._get_asset_by_name(workspace_id, asset_name)
            if asset is None:
                raise AppException(status_code=409, code="FONT_ASSET_NOT_FOUND", detail=f"字体资源 {asset_name} 不存在。")
            self.session.add(
                WorkspaceFontConfig(
                    workspace_id=workspace_id,
                    asset_id=asset.id,
                    asset_name=asset.name,
                    font_family=str(item["font_family"]).strip(),
                    font_format=str(item["font_format"]).strip(),
                    font_weight=str(item["font_weight"]).strip(),
                    font_style=str(item["font_style"]).strip(),
                    font_display=str(item["font_display"]).strip(),
                    status=str(item.get("status") or RecordStatus.ACTIVE.value),
                )
            )
        await self.session.flush()

    async def _import_components(
        self,
        workspace_id: int,
        package_components: list[PackageComponent],
        operator_id: int,
    ) -> list[WorkspaceComponent]:
        """按依赖顺序导入组件并发布为本地 v1。"""

        imported: list[WorkspaceComponent] = []
        code_mapping: dict[tuple[str, int], str] = {}
        for package_component in self._topological_sort_package_components(package_components):
            content = self._rewrite_component_imports(package_component.content, code_mapping)
            preview_schema = self._rewrite_component_imports(package_component.preview_schema or "", code_mapping)
            metadata = package_component.metadata
            now = utc_now()
            component = WorkspaceComponent(
                workspace_id=workspace_id,
                code=await generate_code(self.session, WorkspaceComponent, CODE_PREFIX_COMPONENT),
                content=normalize_text_to_lf(content),
                preview_schema=validate_component_preview_schema_text(preview_schema),
                current_version_no=0,
                draft_base_version_no=0,
                file_type=PageFileType.VUE.value,
                name=str(metadata["name"]).strip(),
                import_name=str(metadata["import_name"]).strip(),
                component_type=str(metadata.get("component_type") or WorkspaceComponentType.CONTENT_BLOCK.value),
                summary=metadata.get("summary"),
                status=RecordStatus.ACTIVE.value,
                created_by=operator_id,
                updated_by=operator_id,
                created_at=now,
                updated_at=now,
            )
            self.session.add(component)
            await self.session.flush()
            await self.component_version_service.publish_draft(
                component=component,
                operator_id=operator_id,
                release_name="离线导入",
                change_note=f"从组件分享包导入：{package_component.source_component_code} v{package_component.source_version_no}",
            )
            imported.append(component)
            code_mapping[(package_component.source_component_code, package_component.source_version_no)] = component.code
        return imported

    async def _validate_component_imports(
        self,
        workspace_id: int,
        components: list[PackageComponent],
        errors: list[str],
    ) -> None:
        """校验组件源码 import 边界和目标工作空间 import_name 冲突。"""

        seen_import_names: set[str] = set()
        component_key_set = {(item.source_component_code, item.source_version_no) for item in components}
        for package_component in components:
            import_name = str(package_component.metadata.get("import_name") or "").strip()
            if import_name in seen_import_names:
                errors.append(f"分享包内存在重复 import_name：{import_name}。")
            seen_import_names.add(import_name)
            existing = await self.component_repository.get_active_by_import_name(
                workspace_id=workspace_id,
                import_name=import_name,
            )
            if existing is not None:
                errors.append(f"目标工作空间已存在 import_name 为 {import_name} 的启用组件。")
            try:
                parsed = self.component_version_service.dependency_service.parse_dependencies(
                    package_component.content,
                    source_label=f"分享包组件 {package_component.source_component_code}",
                    importer_module_path=f"src/workspace-components/{package_component.source_component_code}/v/{package_component.source_version_no}.vue",
                )
            except AppException as error:
                errors.append(str(error.detail))
                continue
            for component_code, version_no in parsed.component_imports:
                if (component_code, version_no) not in component_key_set:
                    errors.append(f"组件 {package_component.source_component_code} 依赖缺失：{component_code} v{version_no}。")

    def _validate_package_dependency_closure(self, components: list[PackageComponent], errors: list[str]) -> None:
        """校验 component.json 中声明的依赖均在包内存在。"""

        component_key_set = {(item.source_component_code, item.source_version_no) for item in components}
        for component in components:
            for dependency in component.dependencies:
                if dependency not in component_key_set:
                    errors.append(f"组件 {component.source_component_code} 的声明依赖不在包内：{dependency[0]} v{dependency[1]}。")

    def _validate_package_font_assets(self, parsed: ParsedPackage, errors: list[str]) -> None:
        """校验字体配置引用的字体资源在包内存在。"""

        asset_names = {str(item.metadata.get("name") or "").strip() for item in parsed.assets}
        for font_config in parsed.font_configs:
            asset_name = str(font_config.get("asset_name") or "").strip()
            if asset_name and asset_name not in asset_names:
                errors.append(f"字体配置引用的资源不在包内：{asset_name}。")

    def _build_component_summaries(
        self,
        components: list[PackageComponent],
        errors: list[str],
    ) -> list[ComponentSharePackageComponentSummary]:
        """构建组件预检摘要。"""

        summaries: list[ComponentSharePackageComponentSummary] = []
        for component in components:
            metadata = component.metadata
            required_fields = ["name", "import_name", "component_type"]
            missing = [field for field in required_fields if not str(metadata.get(field) or "").strip()]
            if missing:
                errors.append(f"组件 {component.source_component_code} 元数据缺少字段：{', '.join(missing)}。")
            if not re.match(COMPONENT_IMPORT_NAME_PATTERN, str(metadata.get("import_name") or "").strip()):
                errors.append(f"组件 {component.source_component_code} 的 import_name 不合法。")
            try:
                WorkspaceComponentType(str(metadata.get("component_type") or ""))
            except ValueError:
                errors.append(f"组件 {component.source_component_code} 的 component_type 不受支持。")
            summaries.append(
                ComponentSharePackageComponentSummary(
                    source_component_code=component.source_component_code,
                    source_version_no=component.source_version_no,
                    name=str(metadata.get("name") or "").strip(),
                    import_name=str(metadata.get("import_name") or "").strip(),
                    component_type=str(metadata.get("component_type") or "").strip(),
                    dependencies=[f"{code}@v{version_no}" for code, version_no in component.dependencies],
                )
            )
        return summaries

    async def _build_asset_summaries(
        self,
        workspace_id: int,
        package_assets: list[PackageAsset],
        errors: list[str],
    ) -> list[ComponentSharePackageAssetSummary]:
        """构建资源预检摘要，并校验同名资源冲突。"""

        summaries: list[ComponentSharePackageAssetSummary] = []
        seen_names: set[str] = set()
        for package_asset in package_assets:
            metadata = package_asset.metadata
            name = str(metadata.get("name") or "").strip()
            file_hash = str(metadata.get("file_hash") or "").strip()
            actual_hash = hashlib.sha256(package_asset.content).hexdigest()
            missing = [
                field
                for field in ["name", "original_name", "asset_type", "file_hash"]
                if not str(metadata.get(field) or "").strip()
            ]
            if missing:
                errors.append(f"资源元数据缺少字段：{', '.join(missing)}。")
            if not name:
                errors.append("资源元数据缺少 name。")
            if name in seen_names:
                errors.append(f"分享包内存在重复资源 name：{name}。")
            seen_names.add(name)
            if file_hash != actual_hash:
                errors.append(f"资源 {name} 的 file_hash 与文件内容不一致。")
            try:
                asset_type = AssetType(str(metadata.get("asset_type") or ""))
                AssetService._validate_asset_file_type(asset_type, str(metadata.get("original_name") or ""), metadata.get("content_type"))
                AssetService._validate_uploaded_asset_content(asset_type, str(metadata.get("original_name") or ""), package_asset.content)
            except ValueError:
                errors.append(f"资源 {name} 的 asset_type 不受支持。")
            except AppException as error:
                errors.append(str(error.detail))
            existing = await self._get_asset_by_name(workspace_id, name)
            action = "create"
            if existing is not None:
                if existing.file_hash != file_hash:
                    errors.append(f'目标工作空间已存在同名但内容不同的资源 "{name}"。')
                action = "reuse"
            summaries.append(
                ComponentSharePackageAssetSummary(
                    name=name,
                    original_name=str(metadata.get("original_name") or "").strip(),
                    asset_type=str(metadata.get("asset_type") or "").strip(),
                    file_hash=file_hash,
                    action=action,
                )
            )
        return summaries

    async def _build_font_summaries(
        self,
        workspace_id: int,
        font_configs: list[dict[str, Any]],
        errors: list[str],
    ) -> list[ComponentSharePackageFontSummary]:
        """构建字体预检摘要，并校验同名配置冲突。"""

        summaries: list[ComponentSharePackageFontSummary] = []
        seen_names: set[str] = set()
        for item in font_configs:
            asset_name = str(item.get("asset_name") or "").strip()
            missing = [
                field
                for field in ["asset_name", "font_family", "font_format", "font_weight", "font_style", "font_display", "status"]
                if not str(item.get(field) or "").strip()
            ]
            if missing:
                errors.append(f"字体配置缺少字段：{', '.join(missing)}。")
            if asset_name in seen_names:
                errors.append(f"分享包内存在重复字体配置：{asset_name}。")
            seen_names.add(asset_name)
            existing = await self._get_font_config_by_asset_name(workspace_id, asset_name)
            action = "create"
            if existing is not None:
                if not self._font_config_matches(existing, item):
                    errors.append(f'目标工作空间已存在同名但配置不同的字体 "{asset_name}"。')
                action = "reuse"
            summaries.append(
                ComponentSharePackageFontSummary(
                    asset_name=asset_name,
                    font_family=str(item.get("font_family") or "").strip(),
                    font_format=str(item.get("font_format") or "").strip(),
                    font_weight=str(item.get("font_weight") or "").strip(),
                    font_style=str(item.get("font_style") or "").strip(),
                    font_display=str(item.get("font_display") or "").strip(),
                    status=str(item.get("status") or "").strip(),
                    action=action,
                )
            )
        return summaries

    async def _list_exportable_assets(self, workspace_id: int) -> list[WorkspaceAsset]:
        """列出可导出的 active 普通资源。"""

        result = await self.session.scalars(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceAsset.source_asset_id.is_(None))
        )
        return list(result.all())

    async def _get_asset_by_name(self, workspace_id: int, name: str) -> WorkspaceAsset | None:
        """按资源逻辑名读取工作空间资源。"""

        return await self.session.scalar(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.name == name)
        )

    async def _get_font_config_by_asset_name(self, workspace_id: int, asset_name: str) -> WorkspaceFontConfig | None:
        """按字体资源逻辑名读取字体配置。"""

        return await self.session.scalar(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.asset_name == asset_name)
        )

    def _collect_asset_names_from_sources(self, sources: list[str]) -> list[str]:
        """从源码和 preview_schema 中按已知资源名收集静态引用。"""

        joined_source = "\n".join(sources)
        return sorted({
            match.group("single") or match.group("double")
            for match in re.finditer(
                r"\b(?:useAssetSrc|useAssetBackground|resolveResourcePath)\s*\(\s*(?:'(?P<single>(?:\\.|[^'\\])*)'|\"(?P<double>(?:\\.|[^\"\\])*)\")",
                joined_source,
                flags=re.DOTALL,
            )
            if match.group("single") or match.group("double")
        })

    def _topological_sort_package_components(self, components: list[PackageComponent]) -> list[PackageComponent]:
        """按包内组件依赖拓扑排序，依赖组件排在使用方前面。"""

        component_map = {(item.source_component_code, item.source_version_no): item for item in components}
        ordered: list[PackageComponent] = []
        visited: set[tuple[str, int]] = set()
        visiting: set[tuple[str, int]] = set()

        def visit(component: PackageComponent) -> None:
            key = (component.source_component_code, component.source_version_no)
            if key in visited:
                return
            if key in visiting:
                raise AppException(status_code=409, code="COMPONENT_DEPENDENCY_CYCLE_DETECTED", detail="分享包组件依赖存在循环。")
            visiting.add(key)
            for dependency in component.dependencies:
                dependency_component = component_map.get(dependency)
                if dependency_component is not None:
                    visit(dependency_component)
            visiting.remove(key)
            visited.add(key)
            ordered.append(component)

        for component in components:
            visit(component)
        return ordered

    @staticmethod
    def _rewrite_component_imports(source: str, code_mapping: dict[tuple[str, int], str]) -> str:
        """将包内旧组件导入路径重写为目标工作空间的新组件 v1 路径。"""

        def replace(match: re.Match[str]) -> str:
            key = (match.group("component_code"), int(match.group("version_no")))
            new_code = code_mapping.get(key)
            if not new_code:
                return match.group(0)
            suffix = ".vue" if match.group(0).endswith(".vue") else ""
            return f"@workspace-components/{new_code}/v/1{suffix}"

        return COMPONENT_IMPORT_PATTERN.sub(replace, source or "")

    @staticmethod
    def _collect_component_refs_from_text(source: str) -> set[tuple[str, int]]:
        """从源码或 preview_schema 文本中收集工作空间组件引用。"""

        result: set[tuple[str, int]] = set()
        for match in COMPONENT_IMPORT_PATTERN.finditer(source or ""):
            result.add((match.group("component_code"), int(match.group("version_no"))))
        return result

    @staticmethod
    def _resolve_package_component_codes(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析包内组件编码。"""

        component_codes = [
            str(item.get("source_component_code") or item.get("component_code") or "").strip()
            for item in manifest.get("components", [])
            if isinstance(item, dict)
        ]
        if not component_codes:
            component_codes = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "components"
            })
        return [code for code in dict.fromkeys(component_codes) if code]

    @staticmethod
    def _resolve_package_asset_hashes(manifest: dict[str, Any], names: set[str]) -> list[str]:
        """从 manifest 或目录结构解析包内资源 hash。"""

        asset_hashes = [
            str(item.get("file_hash") or "").strip()
            for item in manifest.get("assets", [])
            if isinstance(item, dict)
        ]
        if not asset_hashes:
            asset_hashes = sorted({
                parts[1]
                for name in names
                if (parts := name.split("/")) and len(parts) >= 3 and parts[0] == "assets"
            })
        return [file_hash for file_hash in dict.fromkeys(asset_hashes) if file_hash]

    def _read_package_component(self, archive: zipfile.ZipFile, component_code: str) -> PackageComponent:
        """读取包内单个组件。"""

        base_path = f"components/{component_code}"
        metadata = self._read_json(archive, f"{base_path}/component.json")
        if not isinstance(metadata, dict):
            raise AppException(status_code=400, code="COMPONENT_SHARE_COMPONENT_INVALID", detail=f"{base_path}/component.json 必须是 JSON 对象。")
        content = self._read_text(archive, f"{base_path}/index.vue")
        preview_schema_text = self._read_text(archive, f"{base_path}/preview.schema.json")
        dependencies = [
            (str(item.get("component_code") or "").strip(), self._coerce_int(item.get("version_no")) or 0)
            for item in metadata.get("dependencies", [])
            if isinstance(item, dict)
        ]
        dependency_set = {
            item
            for item in dependencies
            if item[0] and item[1] > 0
        }
        dependency_set.update(self._collect_component_refs_from_text(content))
        dependency_set.update(self._collect_component_refs_from_text(preview_schema_text))
        return PackageComponent(
            source_component_code=str(metadata.get("source_component_code") or component_code).strip(),
            source_version_no=self._coerce_int(metadata.get("source_version_no")) or 1,
            metadata=metadata,
            content=content,
            preview_schema=validate_component_preview_schema_text(preview_schema_text),
            dependencies=sorted(dependency_set),
            asset_names=[str(item).strip() for item in metadata.get("asset_names", []) if str(item).strip()],
            font_asset_names=[str(item).strip() for item in metadata.get("font_asset_names", []) if str(item).strip()],
        )

    def _read_package_asset(self, archive: zipfile.ZipFile, asset_hash: str) -> PackageAsset:
        """读取包内单个资源。"""

        base_path = f"assets/{asset_hash}"
        metadata = self._read_json(archive, f"{base_path}/asset.json")
        if not isinstance(metadata, dict):
            raise AppException(status_code=400, code="COMPONENT_SHARE_ASSET_INVALID", detail=f"{base_path}/asset.json 必须是 JSON 对象。")
        original_name = self._safe_archive_filename(str(metadata.get("original_name") or "asset.bin"))
        content = self._read_bytes(archive, f"{base_path}/{original_name}")
        return PackageAsset(metadata=metadata, content=content)

    def _read_json(self, archive: zipfile.ZipFile, name: str) -> dict[str, Any] | list[Any]:
        """从 Zip 中读取 JSON 文件。"""

        try:
            return json.loads(self._read_text(archive, name))
        except json.JSONDecodeError as error:
            raise AppException(status_code=400, code="COMPONENT_SHARE_JSON_INVALID", detail=f"{name} 不是合法 JSON。") from error

    def _read_text(self, archive: zipfile.ZipFile, name: str) -> str:
        """从 Zip 中读取 UTF-8 文本。"""

        try:
            return self._read_bytes(archive, name).decode("utf-8")
        except UnicodeDecodeError as error:
            raise AppException(status_code=400, code="COMPONENT_SHARE_TEXT_INVALID", detail=f"{name} 不是合法 UTF-8 文本。") from error

    @staticmethod
    def _read_bytes(archive: zipfile.ZipFile, name: str) -> bytes:
        """从 Zip 中读取二进制文件并校验路径存在。"""

        normalized_name = ComponentSharePackageService._normalize_zip_name(name)
        try:
            return archive.read(normalized_name)
        except KeyError as error:
            raise AppException(status_code=400, code="COMPONENT_SHARE_FILE_MISSING", detail=f"分享包缺少文件：{normalized_name}。") from error

    @staticmethod
    def _normalize_zip_name(name: str) -> str:
        """标准化 Zip 内部路径，禁止绝对路径和上级目录。"""

        normalized = posixpath.normpath(str(name or "").replace("\\", "/")).lstrip("/")
        if normalized == "." or normalized.startswith("../") or "/../" in normalized:
            raise AppException(status_code=400, code="COMPONENT_SHARE_PATH_INVALID", detail="分享包包含非法路径。")
        return normalized

    @staticmethod
    def _build_component_payload(snapshot: ExportComponentSnapshot) -> dict[str, Any]:
        """构建 component.json 内容。"""

        return {
            "source_component_code": snapshot.component.code,
            "source_version_no": snapshot.version.version_no,
            "name": snapshot.component.name,
            "import_name": snapshot.component.import_name,
            "component_type": snapshot.component.component_type,
            "summary": snapshot.component.summary,
            "file_type": snapshot.version.file_type,
            "dependencies": [
                {"component_code": code, "version_no": version_no}
                for code, version_no in snapshot.dependencies
            ],
            "asset_names": snapshot.asset_names,
            "font_asset_names": snapshot.font_asset_names,
        }

    @staticmethod
    def _build_component_manifest_entry(snapshot: ExportComponentSnapshot) -> dict[str, Any]:
        """构建 manifest.components 中的组件摘要。"""

        return {
            "source_component_code": snapshot.component.code,
            "source_version_no": snapshot.version.version_no,
            "name": snapshot.component.name,
            "import_name": snapshot.component.import_name,
        }

    @staticmethod
    def _build_asset_payload(asset: WorkspaceAsset) -> dict[str, Any]:
        """构建 asset.json 内容。"""

        return {
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "content_type": asset.content_type,
            "file_size": asset.file_size,
            "file_hash": asset.file_hash,
            "description": asset.description,
            "tags": asset.tags or [],
            "render_metadata": asset.render_metadata,
        }

    @staticmethod
    def _build_asset_manifest_entry(asset: WorkspaceAsset) -> dict[str, Any]:
        """构建 manifest.assets 中的资源摘要。"""

        return {
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "file_hash": asset.file_hash,
        }

    @staticmethod
    def _build_font_config_payload(font_config: WorkspaceFontConfig) -> dict[str, Any]:
        """构建字体配置分享包载荷。"""

        return {
            "asset_name": font_config.asset_name,
            "font_family": font_config.font_family,
            "font_format": font_config.font_format,
            "font_weight": font_config.font_weight,
            "font_style": font_config.font_style,
            "font_display": font_config.font_display,
            "status": font_config.status,
        }

    @staticmethod
    def _font_config_matches(existing: WorkspaceFontConfig, payload: dict[str, Any]) -> bool:
        """判断目标工作空间已有字体配置是否与分享包一致。"""

        return all(
            str(getattr(existing, field) or "").strip() == str(payload.get(field) or "").strip()
            for field in ["asset_name", "font_family", "font_format", "font_weight", "font_style", "font_display", "status"]
        )

    @staticmethod
    def _assert_unique_asset_hash_metadata(assets: list[WorkspaceAsset]) -> None:
        """避免同一 hash 对应多个逻辑资源时无法按 v1 包格式表达。"""

        by_hash: dict[str, str] = {}
        for asset in assets:
            existing_name = by_hash.get(asset.file_hash)
            if existing_name is not None and existing_name != asset.name:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_SHARE_ASSET_HASH_CONFLICT",
                    detail=(
                        f"资源 {existing_name} 与 {asset.name} 使用同一文件 hash，"
                        "初版分享包无法表达一份文件对应多个资源名，请先调整资源。"
                    ),
                )
            by_hash[asset.file_hash] = asset.name

    @staticmethod
    def _safe_archive_filename(name: str) -> str:
        """把资源展示文件名规整为 Zip 内单文件名。"""

        filename = Path(str(name or "asset.bin").replace("\\", "/")).name
        return filename or "asset.bin"

    @staticmethod
    def _dump_json(value: Any) -> str:
        """按项目约定输出 UTF-8 友好的格式化 JSON。"""

        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        """把输入值转为整数，失败时返回空。"""

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_export_filename(root_components: list[WorkspaceComponent]) -> str:
        """生成分享包下载文件名。"""

        first_code = root_components[0].code if root_components else "components"
        suffix = f"-and-{len(root_components) - 1}" if len(root_components) > 1 else ""
        return f"workspace-components-{first_code}{suffix}.zip"
