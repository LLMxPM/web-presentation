"""文件功能：构建、预检、预览和导入项目模板包，复用现有组件、资源、主题和 Runtime artifact 能力。"""

from __future__ import annotations

import hashlib
import io
import re
import struct
import uuid
import zlib
import zipfile
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_PAGE, CODE_PREFIX_PROJECT, generate_code
from app.core.exceptions import AppException
from app.core.runtime_module_policy import build_runtime_module_resolver_config, load_runtime_kit_manifest
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import PageFileType, ProjectRouteType, RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.page import Page
from app.models.project_route import ProjectRoute
from app.models.project_suggested_component import ProjectSuggestedComponent
from app.models.project_suggested_reference_asset import ProjectSuggestedReferenceAsset
from app.models.workspace import Project
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_theme import WorkspaceTheme
from app.repositories.page_repository import PageRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.project_route_repository import ProjectRouteRepository
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.asset import resolve_asset_role
from app.schemas.component import (
    ComponentShareExportAssetSummary,
    ComponentShareExportComponentSummary,
    ComponentSharePackageComponentSummary,
)
from app.schemas.project import ProjectBuildExtraAssetsConfig, normalize_project_build_extra_assets_config
from app.schemas.project_template import (
    PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION,
    PROJECT_TEMPLATE_PACKAGE_TYPE,
    ProjectTemplateExportRequest,
    ProjectTemplateExportValidationResult,
    ProjectTemplateImportResult,
    ProjectTemplateImportValidationResult,
    ProjectTemplatePackagePageSummary,
    ProjectTemplatePackageProjectSummary,
    ProjectTemplateScreenshotItem,
    ProjectTemplateScreenshotSummary,
)
from app.schemas.release import PreviewArtifactResponse, PreviewEntryDescriptor
from app.schemas.workspace_style import WorkspaceStylePackageThemeSummary
from app.services.asset_render_metadata_service import AssetRenderMetadataService
from app.services.asset_service import AssetService
from app.services.component_share_package_service import ComponentSharePackageService
from app.services.component_share_package_models import (
    COMPONENT_IMPORT_PATTERN,
    ExportAssetCollection,
    ExportComponentSnapshot,
    PackageAsset,
    PackageComponent,
)
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_job_service import PageScreenshotJobService
from app.services.page_version_service import PageVersionService
from app.services.project_artifact_builder import ProjectArtifactBuilder
from app.services.project_config_service import ProjectConfigService
from app.services.project_route_service import ProjectRouteService
from app.services.project_template_package_format import (
    PackageTemplatePage,
    ParsedProjectTemplatePackage,
    ProjectTemplatePackageFormat,
)
from app.services.resource_reference_parser import ResourceReferenceParser
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService
from app.services.workspace_font_service import WorkspaceFontService
from app.services.workspace_style_package_service import WorkspaceStylePackageService
from app.services.workspace_theme_service import WorkspaceThemeService
from app.core.config import get_settings


@dataclass(slots=True)
class ProjectTemplateExportPlan:
    """模板包导出计划，汇总项目快照、依赖闭包和预检信息。"""

    project: Project
    pages: list[Page]
    routes: list[ProjectRoute]
    component_snapshots: list[ExportComponentSnapshot]
    component_asset_collection: ExportAssetCollection
    assets: list[WorkspaceAsset]
    themes: list[WorkspaceTheme]
    font_configs: list[WorkspaceFontConfig]
    automatic_asset_names: list[str]
    manual_asset_names: list[str]
    missing_asset_names: list[str]
    dynamic_resource_modules: list[str]
    warnings: list[str]


class ProjectTemplatePackageService:
    """项目模板包服务，负责项目级快照导出、导入和临时预览。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_repository = ProjectRepository(session)
        self.page_repository = PageRepository(session)
        self.route_repository = ProjectRouteRepository(session)
        self.workspace_repository = WorkspaceRepository(session)
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)
        self.asset_service = AssetService(session)
        self.component_package_service = ComponentSharePackageService(session)
        self.style_package_service = WorkspaceStylePackageService(session)
        self.object_storage_service = ObjectStorageService()
        self.project_config_service = ProjectConfigService(session)

    async def validate_export_package(
        self,
        *,
        project_id: int,
        payload: ProjectTemplateExportRequest,
    ) -> ProjectTemplateExportValidationResult:
        """预检项目模板包导出内容，不生成 ZIP。"""

        plan = await self._prepare_export_plan(project_id=project_id, payload=payload)
        return await self._build_export_validation(plan, payload)

    async def export_package(
        self,
        *,
        project_id: int,
        payload: ProjectTemplateExportRequest,
        current_user_id: int,
        current_user_display_name: str,
    ) -> tuple[bytes, str]:
        """导出项目模板包，返回 ZIP 内容和下载文件名。"""

        if payload.refresh_screenshots:
            await self._refresh_project_screenshots_best_effort(project_id, current_user_id)
        plan = await self._prepare_export_plan(project_id=project_id, payload=payload)
        validation = await self._build_export_validation(plan, payload)
        if not validation.can_export:
            raise AppException(
                status_code=400,
                code="PROJECT_TEMPLATE_EXPORT_INVALID",
                detail="项目导出预检未通过：" + "；".join(validation.errors),
            )
        archive_content = await self._build_zip_archive(plan, payload, validation, current_user_display_name)
        return archive_content, self._build_export_filename(validation.project.name)

    async def validate_import_package(
        self,
        *,
        workspace_id: int,
        archive_content: bytes,
    ) -> ProjectTemplateImportValidationResult:
        """预检模板包导入，不写入数据库。"""

        parsed = ProjectTemplatePackageFormat.parse_package(archive_content)
        return await self._validate_parsed_package(workspace_id, parsed)

    async def import_package(
        self,
        *,
        workspace_id: int,
        archive_content: bytes,
        operator_id: int,
    ) -> ProjectTemplateImportResult:
        """正式导入模板包，创建新项目、页面和路由。"""

        parsed = ProjectTemplatePackageFormat.parse_package(archive_content)
        validation = await self._validate_parsed_package(workspace_id, parsed)
        if not validation.valid:
            raise AppException(
                status_code=400,
                code="PROJECT_TEMPLATE_IMPORT_INVALID",
                detail="项目导入预检未通过：" + "；".join(validation.errors),
            )

        await self.component_package_service._import_assets(workspace_id, parsed.assets)
        await self.component_package_service._import_font_configs(workspace_id, parsed.font_configs)
        await self.style_package_service._import_themes(workspace_id, parsed.themes, operator_id)
        _, component_mapping, component_summaries = await self.component_package_service.import_or_reuse_components(
            workspace_id,
            parsed.components,
            parsed.assets,
            parsed.font_configs,
            operator_id,
            release_name="项目导入",
            change_note_prefix="从导入项目创建",
        )
        project, page_mapping = await self._create_project_from_package(
            workspace_id=workspace_id,
            parsed=parsed,
            component_mapping=component_mapping,
            operator_id=operator_id,
        )
        await self.session.commit()
        return ProjectTemplateImportResult(
            project_id=project.id,
            project_code=project.code,
            project_name=project.name,
            page_ids=[page.id for page in page_mapping.values()],
            pages=validation.pages,
            components=component_summaries,
            assets=validation.assets,
            themes=validation.themes,
            fonts=validation.fonts,
            warnings=validation.warnings,
        )

    async def create_package_preview_artifact(
        self,
        *,
        workspace_id: int,
        archive_content: bytes,
        tenant_id: str,
    ) -> PreviewArtifactResponse:
        """基于上传模板包生成短生命周期预览 artifact，不写入项目表。"""

        parsed = ProjectTemplatePackageFormat.parse_package(archive_content)
        validation = await self._validate_parsed_package(workspace_id, parsed, allow_target_conflicts=True)
        if validation.errors:
            raise AppException(
                status_code=400,
                code="PROJECT_TEMPLATE_PREVIEW_INVALID",
                detail="项目预览预检未通过：" + "；".join(validation.errors),
            )

        settings = get_settings()
        artifact_id = f"tpl_{uuid.uuid4().hex}"
        asset_base_url = f"{settings.backend_public_base_url.rstrip('/')}/public/template-package-assets/{artifact_id}"
        page_config = self._build_page_config(parsed.project)
        config_bundle = self._build_preview_config_bundle(parsed)
        modules_metadata, modules_data = self._build_preview_modules(parsed)
        entry_descriptor = self._resolve_preview_entry(parsed)
        manifest = {
            "artifact_kind": "project_template_preview",
            "tenant_id": tenant_id,
            "preview_kind": "project",
            "owner_scope": {"scope_type": "template_package", "workspace_id": str(workspace_id)},
            "entry_descriptor": entry_descriptor.model_dump(mode="python", exclude_none=True),
            "asset_base_url": asset_base_url,
            "modules": modules_metadata,
            "assets": self._build_package_asset_mapping(parsed.assets),
            "asset_metadata": self._build_package_asset_metadata(parsed.assets),
        }
        store = RuntimeArtifactStore()
        await store.put_artifact(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            project_id=None,
            artifact_kind="project_template_preview",
            manifest=manifest,
            config_bundle=config_bundle,
            modules_data=modules_data,
            artifact_id=artifact_id,
        )
        await store.put_asset_blobs(
            artifact_id=artifact_id,
            assets={
                str(asset.metadata.get("file_hash") or ""): {
                    "content": asset.content,
                    "content_type": asset.metadata.get("content_type"),
                    "original_name": asset.metadata.get("original_name"),
                }
                for asset in parsed.assets
                if str(asset.metadata.get("file_hash") or "").strip()
            },
        )
        preview_token = TokenService.generate_preview_context_token(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            preview_kind="project",
            scope_type="template_package",
            workspace_id=workspace_id,
            project_id=None,
            entry_descriptor=entry_descriptor.model_dump(mode="python", exclude_none=True),
            asset_base_url=asset_base_url,
            trace_id=f"req-{uuid.uuid4().hex[:8]}",
        )
        preview_url = f"{settings.backend_public_base_url.rstrip('/')}/preview/artifacts/{artifact_id}?{urlencode({'token': preview_token})}"
        return PreviewArtifactResponse(
            preview_url=preview_url,
            artifact_id=artifact_id,
            preview_kind="project",
            entry_descriptor=entry_descriptor,
            viewport_width=page_config["width"],
            viewport_height=page_config["height"],
            workspace_id=workspace_id,
        )

    async def _prepare_export_plan(
        self,
        *,
        project_id: int,
        payload: ProjectTemplateExportRequest,
    ) -> ProjectTemplateExportPlan:
        """准备模板包导出所需项目、页面、组件闭包、资源、主题和字体。"""

        project = await self._get_active_project_or_raise(project_id)
        pages = await self._list_project_pages(project.id)
        routes = await self.route_repository.list_by_project(project.id)
        component_snapshots = await self._build_component_snapshot_closure(project.workspace_id, project.id, pages)
        component_asset_collection = await self.component_package_service._collect_export_assets(
            project.workspace_id,
            component_snapshots,
            manual_asset_names=payload.manual_asset_names,
        )
        component_font_configs = await self.component_package_service._collect_export_font_configs(
            project.workspace_id,
            component_snapshots,
        )
        themes = await self._collect_project_themes(project)
        theme_assets, theme_font_configs = await self._collect_theme_dependencies(project.workspace_id, themes)
        page_asset_names, dynamic_resource_modules = self._collect_page_asset_references(pages)
        config_asset_names = await self._collect_project_config_asset_names(project)
        suggested_asset_names = await self._collect_project_suggested_asset_names(project.id)
        extra_asset_names = normalize_project_build_extra_assets_config(project.build_extra_assets_json).asset_names
        automatic_asset_names = self._deduplicate_names(
            [
                *page_asset_names,
                *config_asset_names,
                *suggested_asset_names,
                *extra_asset_names,
                *[asset.name for asset in theme_assets],
                *component_asset_collection.automatic_asset_names,
            ]
        )
        manual_names = [
            name
            for name in component_asset_collection.manual_asset_names
            if name not in set(automatic_asset_names)
        ]
        asset_by_name = await self._list_workspace_assets_by_name(project.workspace_id)
        missing_static_names = [
            name for name in automatic_asset_names if name not in asset_by_name
        ]
        missing_manual_names = list(component_asset_collection.missing_manual_asset_names)
        selected_assets = [
            asset_by_name[name]
            for name in self._deduplicate_names([*automatic_asset_names, *manual_names])
            if name in asset_by_name
        ]
        font_configs = self._deduplicate_font_configs([*theme_font_configs, *component_font_configs])
        assets = self._deduplicate_assets([*theme_assets, *component_asset_collection.assets, *selected_assets])
        return ProjectTemplateExportPlan(
            project=project,
            pages=pages,
            routes=routes,
            component_snapshots=component_snapshots,
            component_asset_collection=component_asset_collection,
            assets=assets,
            themes=themes,
            font_configs=font_configs,
            automatic_asset_names=automatic_asset_names,
            manual_asset_names=manual_names,
            missing_asset_names=self._deduplicate_names([*missing_static_names, *component_asset_collection.missing_static_asset_names, *missing_manual_names]),
            dynamic_resource_modules=self._deduplicate_names([*dynamic_resource_modules, *component_asset_collection.dynamic_resource_components]),
            warnings=list(component_asset_collection.warnings),
        )

    async def _build_export_validation(
        self,
        plan: ProjectTemplateExportPlan,
        payload: ProjectTemplateExportRequest,
    ) -> ProjectTemplateExportValidationResult:
        """把导出计划转换为前端可展示的预检结果。"""

        errors = []
        if not plan.pages:
            errors.append("项目没有可导出的启用页面。")
        if plan.missing_asset_names:
            errors.append("导出项目依赖的资源缺失：" + ", ".join(plan.missing_asset_names))
        automatic_set = set(plan.automatic_asset_names)
        manual_set = set(plan.manual_asset_names)
        screenshots = await self._build_screenshot_summary(plan, payload.cover_page_id)
        return ProjectTemplateExportValidationResult(
            can_export=not errors,
            project=self._build_project_summary(plan.project),
            pages=[self._build_page_summary(page) for page in plan.pages],
            components=[
                ComponentShareExportComponentSummary(
                    source_component_code=snapshot.component.code,
                    source_version_no=snapshot.version.version_no,
                    name=snapshot.component.name,
                    import_name=snapshot.component.import_name,
                    has_dynamic_resources=bool(snapshot.dynamic_resource_component_names),
                    missing_static_asset_names=snapshot.missing_static_asset_names,
                )
                for snapshot in plan.component_snapshots
            ],
            automatic_assets=[
                self._build_export_asset_summary(asset, "automatic")
                for asset in plan.assets
                if asset.name in automatic_set
            ],
            manual_assets=[
                self._build_export_asset_summary(asset, "manual")
                for asset in plan.assets
                if asset.name in manual_set
            ],
            themes=[
                WorkspaceStylePackageThemeSummary(key=theme.key, name=theme.name, action="export")
                for theme in plan.themes
            ],
            fonts=[
                self._build_font_summary(font_config, action="export")
                for font_config in plan.font_configs
            ],
            screenshots=screenshots,
            warnings=plan.warnings,
            errors=errors,
            missing_static_asset_names=plan.missing_asset_names,
            missing_manual_asset_names=plan.component_asset_collection.missing_manual_asset_names,
            dynamic_resource_modules=plan.dynamic_resource_modules,
        )

    async def _build_zip_archive(
        self,
        plan: ProjectTemplateExportPlan,
        payload: ProjectTemplateExportRequest,
        validation: ProjectTemplateExportValidationResult,
        author_display_name: str,
    ) -> bytes:
        """按模板包格式生成 ZIP 内容。"""

        buffer = io.BytesIO()
        runtime_manifest_version = str(load_runtime_kit_manifest().get("version") or "")
        component_fingerprints = self.component_package_service._calculate_export_package_fingerprints(
            snapshots=plan.component_snapshots,
            assets=plan.assets,
            font_configs=plan.font_configs,
        )
        template_payload = self._build_template_metadata(plan, payload, runtime_manifest_version, author_display_name)
        screenshots_payload, screenshot_files = await self._build_screenshot_payload_and_files(plan, payload.cover_page_id)
        project_payload = await self._build_project_payload(plan.project)
        routes_payload = self._build_routes_payload(plan.routes, plan.pages)
        asset_entries = [self._build_asset_payload(asset) for asset in plan.assets]
        font_entries = [self._build_font_payload(item) for item in plan.font_configs]
        theme_entries = [await self._build_theme_payload(theme) for theme in plan.themes]
        component_entries = [
            self.component_package_service._build_component_manifest_entry(
                snapshot,
                component_fingerprints.get((snapshot.component.code, snapshot.version.version_no)),
            )
            for snapshot in plan.component_snapshots
        ]
        manifest = {
            "package_type": PROJECT_TEMPLATE_PACKAGE_TYPE,
            "schema_version": PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION,
            "exported_at": utc_now().isoformat(),
            "runtime_kit_manifest_version": runtime_manifest_version,
            "template_path": "metadata/template.json",
            "screenshots_path": "metadata/screenshots.json",
            "project_path": "project/project.json",
            "routes_path": "project/routes.json",
            "page_count": len(plan.pages),
            "component_count": len(plan.component_snapshots),
            "asset_count": len(plan.assets),
            "theme_count": len(plan.themes),
            "font_count": len(plan.font_configs),
            "pages": [
                {
                    "source_page_code": page.code,
                    "title": page.title,
                    "file_type": page.file_type,
                }
                for page in plan.pages
            ],
            "components": component_entries,
            "assets": [
                {
                    "name": item["name"],
                    "original_name": item["original_name"],
                    "asset_type": item["asset_type"],
                    "file_hash": item["file_hash"],
                }
                for item in asset_entries
            ],
            "themes": [{"key": item["key"], "name": item["name"]} for item in theme_entries],
            "fonts": font_entries,
            "warnings": [*validation.warnings, *validation.dynamic_resource_modules],
        }

        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", ProjectTemplatePackageFormat.dump_json(manifest))
            archive.writestr("metadata/template.json", ProjectTemplatePackageFormat.dump_json(template_payload))
            archive.writestr("metadata/screenshots.json", ProjectTemplatePackageFormat.dump_json(screenshots_payload))
            archive.writestr("project/project.json", ProjectTemplatePackageFormat.dump_json(project_payload))
            archive.writestr("project/routes.json", ProjectTemplatePackageFormat.dump_json(routes_payload))
            for page in plan.pages:
                archive.writestr(f"pages/{page.code}/page.json", ProjectTemplatePackageFormat.dump_json(self._build_page_payload(page)))
                archive.writestr(f"pages/{page.code}/index.vue", normalize_text_to_lf(page.page_content))
            for snapshot in plan.component_snapshots:
                base_path = f"components/{snapshot.component.code}"
                fingerprint = component_fingerprints.get((snapshot.component.code, snapshot.version.version_no))
                archive.writestr(
                    f"{base_path}/component.json",
                    ProjectTemplatePackageFormat.dump_json(
                        self.component_package_service._build_component_payload(snapshot, fingerprint)
                    ),
                )
                archive.writestr(f"{base_path}/index.vue", normalize_text_to_lf(snapshot.version.content))
                archive.writestr(f"{base_path}/preview.schema.json", snapshot.version.preview_schema or "{}")
            for theme_payload in theme_entries:
                archive.writestr(f"themes/{theme_payload['key']}.json", ProjectTemplatePackageFormat.dump_json(theme_payload))
            for asset in plan.assets:
                asset_payload = self._build_asset_payload(asset)
                base_path = f"assets/{asset.file_hash}"
                archive.writestr(f"{base_path}/asset.json", ProjectTemplatePackageFormat.dump_json(asset_payload))
                archive.writestr(
                    f"{base_path}/{ProjectTemplatePackageFormat.safe_archive_filename(asset.original_name)}",
                    await self.asset_service.driver.read_content(plan.project.workspace_id, asset.file_name),
                )
            archive.writestr("fonts/font-configs.json", ProjectTemplatePackageFormat.dump_json(font_entries))
            for path, content in screenshot_files.items():
                archive.writestr(path, content)
        return buffer.getvalue()

    async def _validate_parsed_package(
        self,
        workspace_id: int,
        parsed: ParsedProjectTemplatePackage,
        *,
        allow_target_conflicts: bool = False,
    ) -> ProjectTemplateImportValidationResult:
        """对模板包执行跨对象预检并返回前端展示摘要。"""

        errors: list[str] = []
        warnings = [str(item) for item in parsed.manifest.get("warnings", []) if str(item).strip()]
        schema_version = self._coerce_int(parsed.manifest.get("schema_version"))
        runtime_version = str(parsed.manifest.get("runtime_kit_manifest_version") or "").strip()
        if parsed.manifest.get("package_type") != PROJECT_TEMPLATE_PACKAGE_TYPE:
            errors.append("导入文件 package_type 不受支持。")
        if schema_version != PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION:
            errors.append(f"导入文件 schema_version 必须是 {PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION}。")
        if await self.workspace_repository.get_by_id(workspace_id) is None:
            errors.append("目标工作空间不存在。")

        self._validate_template_project_payload(parsed.project, errors)
        page_summaries = self._validate_template_pages(parsed.pages, parsed.routes, errors)
        self._validate_page_component_refs(parsed.pages, parsed.components, errors)
        await self._validate_project_theme_reference(workspace_id, parsed, errors)
        screenshot_summary = self._validate_template_screenshots(parsed.screenshots, parsed.pages, errors)
        asset_summaries = await self.style_package_service._build_asset_summaries(workspace_id, parsed.assets, errors)
        font_summaries = await self.style_package_service._build_font_summaries(workspace_id, parsed.font_configs, parsed.assets, errors)
        theme_summaries = await self.style_package_service._build_theme_summaries(workspace_id, parsed.themes, parsed.assets, parsed.font_configs, errors)
        if allow_target_conflicts:
            errors = [item for item in errors if "目标工作空间已存在" not in item]

        await self.component_package_service._validate_component_imports(workspace_id, parsed.components, errors)
        self.component_package_service._validate_package_dependency_closure(parsed.components, errors)
        self.component_package_service._validate_package_font_assets(
            type("Parsed", (), {"assets": parsed.assets, "font_configs": parsed.font_configs})(),
            errors,
        )
        component_actions = await self.component_package_service._build_component_import_actions(
            workspace_id=workspace_id,
            package_components=parsed.components,
            package_assets=parsed.assets,
            font_configs=parsed.font_configs,
            errors=errors,
        )
        component_summaries = self.component_package_service._build_component_summaries(component_actions)
        if allow_target_conflicts:
            errors = [item for item in errors if "目标工作空间已存在" not in item]

        return ProjectTemplateImportValidationResult(
            valid=not errors,
            schema_version=schema_version,
            runtime_kit_manifest_version=runtime_version or None,
            template=dict(parsed.template),
            project=self._build_project_summary_from_payload(parsed.project),
            pages=page_summaries,
            components=component_summaries,
            assets=asset_summaries,
            themes=theme_summaries,
            fonts=font_summaries,
            screenshots=screenshot_summary,
            errors=errors,
            warnings=warnings,
        )

    async def _create_project_from_package(
        self,
        *,
        workspace_id: int,
        parsed: ParsedProjectTemplatePackage,
        component_mapping: dict[tuple[str, int], WorkspaceComponent],
        operator_id: int,
    ) -> tuple[Project, dict[str, Page]]:
        """把模板包内容写入目标工作空间，返回新项目和页面映射。"""

        project_payload = parsed.project
        project = Project(
            workspace_id=workspace_id,
            code=await generate_code(self.session, Project, CODE_PREFIX_PROJECT),
            name=str(project_payload.get("name") or parsed.template.get("name") or "导入项目").strip(),
            description=project_payload.get("description") or parsed.template.get("summary"),
            status=RecordStatus.ACTIVE.value,
            page_width=int(project_payload.get("page_width") or 1920),
            page_height=int(project_payload.get("page_height") or 1080),
            base_font_size=str(project_payload.get("base_font_size") or "20px"),
            icon_default_stroke_width=int(project_payload.get("icon_default_stroke_width") or 2),
            show_pdf_export_button=bool(project_payload.get("show_pdf_export_button", True)),
            menu_mode=str(project_payload.get("menu_mode") or "preview"),
            theme_key=str(project_payload.get("theme_key") or "").strip() or None,
            theme_config_yaml=str(project_payload.get("theme_config_yaml") or ""),
            style_spec_markdown=str(project_payload.get("style_spec_markdown") or ""),
            build_extra_assets_json=normalize_project_build_extra_assets_config(
                project_payload.get("build_extra_assets_json")
            ).model_dump(mode="python"),
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(project)
        await self.session.flush()

        component_code_mapping = {
            key: component.code
            for key, component in component_mapping.items()
        }
        page_code_mapping = await self._generate_page_code_mapping(parsed.pages)
        page_mapping: dict[str, Page] = {}
        for package_page in parsed.pages:
            page_code = page_code_mapping[package_page.source_page_code]
            content = self._rewrite_page_module_imports(
                self.component_package_service._rewrite_component_imports(package_page.content, component_code_mapping),
                page_code_mapping,
            )
            page = Page(
                code=page_code,
                page_content=normalize_text_to_lf(content),
                current_version_no=1,
                file_type=str(package_page.metadata.get("file_type") or PageFileType.VUE.value),
                title=str(package_page.metadata.get("title") or package_page.source_page_code).strip(),
                summary=package_page.metadata.get("summary"),
                speaker_notes=package_page.metadata.get("speaker_notes"),
                status=RecordStatus.ACTIVE.value,
                workspace_id=workspace_id,
                project_id=project.id,
                created_by=operator_id,
                updated_by=operator_id,
            )
            self.session.add(page)
            await self.session.flush()
            await PageVersionService(self.session).initialize_page_version(page, operator_id, change_note="从导入项目创建")
            page_mapping[package_page.source_page_code] = page

        await self._create_project_routes_from_package(project.id, parsed.routes, page_mapping, operator_id)
        await self._create_project_suggested_assets(project.id, workspace_id, parsed.project)
        await self._create_project_suggested_components(project.id, parsed.project, component_mapping)
        return project, page_mapping

    async def _build_component_snapshot_closure(
        self,
        workspace_id: int,
        project_id: int,
        pages: list[Page],
    ) -> list[ExportComponentSnapshot]:
        """按页面源码和项目建议组件收集组件发布版本闭包。"""

        root_refs: list[tuple[str, int]] = []
        for page in pages:
            root_refs.extend(self._collect_component_refs_from_text(page.page_content))
        root_refs.extend(await self._collect_project_suggested_component_refs(project_id))

        snapshots: list[ExportComponentSnapshot] = []
        visited: set[tuple[str, int]] = set()
        visiting: set[tuple[str, int]] = set()

        async def visit(component_code: str, version_no: int) -> None:
            key = (component_code, version_no)
            if key in visited:
                return
            if key in visiting:
                raise AppException(status_code=409, code="COMPONENT_DEPENDENCY_CYCLE_DETECTED", detail="组件依赖存在循环。")
            visiting.add(key)
            component = await self.component_repository.get_by_code(component_code)
            if component is None or component.workspace_id != workspace_id:
                raise AppException(status_code=409, code="PROJECT_TEMPLATE_COMPONENT_MISSING", detail=f"组件不存在：{component_code} v{version_no}。")
            version = await self.component_version_repository.get_by_component_and_version(component.id, version_no)
            if version is None:
                raise AppException(status_code=409, code="PROJECT_TEMPLATE_COMPONENT_VERSION_MISSING", detail=f"组件版本不存在：{component_code} v{version_no}。")
            dependencies = self._collect_component_refs_from_text(version.content)
            for schema_ref in self._collect_component_refs_from_text(version.preview_schema or ""):
                if schema_ref not in dependencies:
                    dependencies.append(schema_ref)
            for dependency_code, dependency_version in dependencies:
                await visit(dependency_code, dependency_version)
            snapshot = ExportComponentSnapshot(
                component=component,
                version=version,
                dependencies=dependencies,
                asset_names=[],
                font_asset_names=WorkspaceFontService.collect_declared_font_asset_names([version.content]),
                missing_static_asset_names=[],
                dynamic_resource_component_names=[],
            )
            snapshots.append(snapshot)
            visited.add(key)
            visiting.remove(key)

        for component_code, version_no in self._deduplicate_component_refs(root_refs):
            await visit(component_code, version_no)
        return snapshots

    async def _build_project_payload(self, project: Project) -> dict[str, Any]:
        """构建不含数据库 ID 的项目载荷。"""

        suggested_assets = await self._collect_project_suggested_asset_names(project.id)
        suggested_components = await self._collect_project_suggested_component_payloads(project.id)
        runtime_theme_config = await self.project_config_service.resolve_runtime_theme_config(project)
        return {
            "source_project_code": project.code,
            "name": project.name,
            "description": project.description,
            "page_width": project.page_width,
            "page_height": project.page_height,
            "base_font_size": project.base_font_size,
            "icon_default_stroke_width": project.icon_default_stroke_width,
            "show_pdf_export_button": project.show_pdf_export_button,
            "menu_mode": project.menu_mode,
            "theme_key": project.theme_key,
            "theme_config_yaml": yaml.safe_dump(runtime_theme_config, allow_unicode=True, sort_keys=False),
            "style_spec_markdown": project.style_spec_markdown,
            "build_extra_assets_json": normalize_project_build_extra_assets_config(project.build_extra_assets_json).model_dump(mode="python"),
            "suggested_reference_asset_names": suggested_assets,
            "suggested_components": suggested_components,
        }

    @staticmethod
    def _build_page_payload(page: Page) -> dict[str, Any]:
        """构建不含数据库 ID 的页面载荷。"""

        return {
            "source_page_code": page.code,
            "title": page.title,
            "summary": page.summary,
            "speaker_notes": page.speaker_notes,
            "file_type": page.file_type,
        }

    def _build_routes_payload(self, routes: list[ProjectRoute], pages: list[Page]) -> dict[str, Any]:
        """把数据库路由树转为使用 source_page_code 的模板路由载荷。"""

        children_by_parent = ProjectRouteService._group_children(routes)
        page_code_by_id = {page.id: page.code for page in pages}

        def serialize(route: ProjectRoute) -> dict[str, Any]:
            payload = {
                "route_type": route.route_type,
                "route": route.route,
                "order": route.order,
                "hidden": route.hidden,
                "group_title": route.group_title,
                "source_page_code": page_code_by_id.get(route.page_id) if route.page_id is not None else None,
                "children": [],
            }
            if route.route_type == ProjectRouteType.GROUP.value:
                payload["children"] = [serialize(child) for child in ProjectRouteService._sort_routes(children_by_parent.get(route.id, []))]
            return payload

        return {"routes": [serialize(route) for route in ProjectRouteService._sort_routes(children_by_parent.get(None, []))]}

    async def _build_screenshot_summary(
        self,
        plan: ProjectTemplateExportPlan,
        cover_page_id: int | None,
    ) -> ProjectTemplateScreenshotSummary:
        """构建导出预检中的截图摘要。"""

        cover_page = self._resolve_cover_page(plan.pages, plan.routes, cover_page_id)
        return ProjectTemplateScreenshotSummary(
            cover=ProjectTemplateScreenshotItem(
                path="screenshots/cover.png",
                width=plan.project.page_width,
                height=plan.project.page_height,
                source_page_code=cover_page.code if cover_page else None,
                title=cover_page.title if cover_page else None,
                order=1,
            ) if cover_page else None,
            pages=[
                ProjectTemplateScreenshotItem(
                    path=f"screenshots/pages/{page.code}.png",
                    width=plan.project.page_width,
                    height=plan.project.page_height,
                    source_page_code=page.code,
                    title=page.title,
                    order=index + 1,
                )
                for index, page in enumerate(plan.pages)
            ],
        )

    async def _build_screenshot_payload_and_files(
        self,
        plan: ProjectTemplateExportPlan,
        cover_page_id: int | None,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        """构建截图清单并读取截图文件，缺失时写入占位 PNG。"""

        summary = await self._build_screenshot_summary(plan, cover_page_id)
        files: dict[str, bytes] = {}
        page_content_by_code: dict[str, bytes] = {}
        for page in plan.pages:
            page_content_by_code[page.code] = await self._read_or_build_page_screenshot(page, plan.project)
        for item in summary.pages:
            if item.source_page_code:
                files[item.path] = page_content_by_code.get(item.source_page_code) or self._build_placeholder_png(item.width, item.height)
        if summary.cover is not None:
            cover_code = summary.cover.source_page_code
            files[summary.cover.path] = (
                page_content_by_code.get(str(cover_code or ""))
                or self._build_placeholder_png(summary.cover.width, summary.cover.height)
            )
        return summary.model_dump(mode="python"), files

    async def _read_or_build_page_screenshot(self, page: Page, project: Project) -> bytes:
        """读取页面已有截图；缺失或读取失败时返回占位 PNG。"""

        if page.screenshot_storage_key:
            try:
                return await self.object_storage_service.read_object(str(page.screenshot_storage_key))
            except Exception:  # noqa: BLE001
                pass
        return self._build_placeholder_png(project.page_width, project.page_height)

    async def _refresh_project_screenshots_best_effort(self, project_id: int, user_id: int) -> None:
        """尽力刷新项目截图，失败不阻断模板包导出。"""

        try:
            from app.services.auth_service import AuthContext
            from app.models.user import User

            user = await self.session.scalar(select(User).where(User.id == user_id))
            if user is None:
                return
            # 模板导出只补投截图任务，不在导出请求中直接启动 Chromium。
            await PageScreenshotJobService(self.session).create_batch_refresh_screenshot_jobs(
                project_id=project_id,
                current=AuthContext(user=user, session_token="", backend_session_id="template-export"),
                source="template_export",
            )
        except Exception:  # noqa: BLE001
            await self.session.rollback()

    @staticmethod
    def _build_placeholder_png(width: int, height: int) -> bytes:
        """生成纯色 PNG 占位图，保证模板包始终包含可展示截图。"""

        resolved_width = max(int(width or 1), 1)
        resolved_height = max(int(height or 1), 1)
        row = b"\x00" + (b"\xf8\xfa\xfc" * resolved_width)
        raw = row * resolved_height

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        return b"".join(
            [
                b"\x89PNG\r\n\x1a\n",
                chunk(b"IHDR", struct.pack(">IIBBBBB", resolved_width, resolved_height, 8, 2, 0, 0, 0)),
                chunk(b"IDAT", zlib.compress(raw, 9)),
                chunk(b"IEND", b""),
            ]
        )

    def _build_template_metadata(
        self,
        plan: ProjectTemplateExportPlan,
        payload: ProjectTemplateExportRequest,
        runtime_manifest_version: str,
        author_display_name: str,
    ) -> dict[str, Any]:
        """合并请求和项目真实字段，生成外部模板库展示元数据。"""

        metadata = payload.metadata
        now = utc_now().isoformat()
        page_width = plan.project.page_width
        page_height = plan.project.page_height
        author = str(author_display_name or "").strip()
        return {
            "slug": metadata.slug or self._slugify(plan.project.name or plan.project.code),
            "name": metadata.name or plan.project.name,
            "summary": metadata.summary or plan.project.description or "",
            "description": metadata.description or plan.project.description,
            "author": author,
            "page_count": len(plan.pages),
            "page_width": page_width,
            "page_height": page_height,
            "aspect_ratio": self._format_aspect_ratio(page_width, page_height),
            "runtime_kit_manifest_version": runtime_manifest_version,
            "created_at": now,
            "updated_at": now,
        }

    async def _create_project_routes_from_package(
        self,
        project_id: int,
        routes_payload: dict[str, Any],
        page_mapping: dict[str, Page],
        operator_id: int,
    ) -> None:
        """根据模板路由载荷创建新项目路由树。"""

        for route_item in routes_payload.get("routes", []):
            if not isinstance(route_item, dict):
                continue
            await self._create_route_item(project_id, route_item, page_mapping, operator_id, parent_id=None)

    async def _create_route_item(
        self,
        project_id: int,
        route_item: dict[str, Any],
        page_mapping: dict[str, Page],
        operator_id: int,
        *,
        parent_id: int | None,
    ) -> None:
        """递归创建路由节点。"""

        route_type = str(route_item.get("route_type") or ProjectRouteType.PAGE.value)
        route = str(route_item.get("route") or "").strip()
        ProjectRouteService._ensure_valid_route_segment(route, source_label="导入项目路由")
        if route_type == ProjectRouteType.GROUP.value:
            group = await self.route_repository.create(
                ProjectRoute(
                    project_id=project_id,
                    parent_id=parent_id,
                    route=route,
                    order=int(route_item.get("order") or 0),
                    hidden=bool(route_item.get("hidden", False)),
                    page_id=None,
                    route_type=ProjectRouteType.GROUP.value,
                    group_title=str(route_item.get("group_title") or route).strip(),
                    created_by=operator_id,
                    updated_by=operator_id,
                )
            )
            for child in route_item.get("children", []):
                if isinstance(child, dict):
                    await self._create_route_item(project_id, child, page_mapping, operator_id, parent_id=group.id)
            return

        source_page_code = str(route_item.get("source_page_code") or "").strip()
        page = page_mapping.get(source_page_code)
        if page is None:
            raise AppException(status_code=400, code="PROJECT_TEMPLATE_ROUTE_PAGE_MISSING", detail=f"导入项目路由引用的页面不存在：{source_page_code}。")
        await self.route_repository.create(
            ProjectRoute(
                project_id=project_id,
                parent_id=parent_id,
                route=route,
                order=int(route_item.get("order") or 0),
                hidden=bool(route_item.get("hidden", False)),
                page_id=page.id,
                route_type=ProjectRouteType.PAGE.value,
                created_by=operator_id,
                updated_by=operator_id,
            )
        )

    async def _create_project_suggested_assets(self, project_id: int, workspace_id: int, project_payload: dict[str, Any]) -> None:
        """按资源 name 恢复项目建议引用资源。"""

        names = [str(item).strip() for item in project_payload.get("suggested_reference_asset_names", []) if str(item).strip()]
        if not names:
            return
        asset_by_name = await self._list_workspace_assets_by_name(workspace_id)
        rows = []
        for index, name in enumerate(self._deduplicate_names(names)):
            asset = asset_by_name.get(name)
            if asset is None:
                continue
            rows.append(ProjectSuggestedReferenceAsset(project_id=project_id, asset_id=asset.id, sort_order=index))
        if rows:
            self.session.add_all(rows)
            await self.session.flush()

    async def _create_project_suggested_components(
        self,
        project_id: int,
        project_payload: dict[str, Any],
        component_mapping: dict[tuple[str, int], WorkspaceComponent],
    ) -> None:
        """按组件映射恢复项目建议组件。"""

        rows = []
        for index, item in enumerate(project_payload.get("suggested_components", [])):
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("source_component_code") or "").strip(),
                self._coerce_int(item.get("source_version_no")) or 1,
            )
            component = component_mapping.get(key)
            if component is None:
                continue
            rows.append(ProjectSuggestedComponent(project_id=project_id, component_id=component.id, sort_order=index))
        if rows:
            self.session.add_all(rows)
            await self.session.flush()

    def _build_preview_config_bundle(self, parsed: ParsedProjectTemplatePackage) -> dict[str, Any]:
        """从模板包构建 Runtime 预览配置包。"""

        return {
            "app": {
                "app": {
                    "title": parsed.project.get("name") or parsed.template.get("name") or "模板预览",
                    "description": parsed.project.get("description") or parsed.template.get("summary") or "",
                    "page": self._build_page_config(parsed.project),
                    "features": {
                        "showPdfExportButton": bool(parsed.project.get("show_pdf_export_button", True)),
                        "menuMode": parsed.project.get("menu_mode") or "preview",
                    },
                },
            },
            "routes": self._build_preview_routes(parsed.routes, parsed.pages),
            "icons": {"static_icons": []},
            "themes": self._parse_theme_config(parsed.project.get("theme_config_yaml")),
            "fonts": self._build_preview_font_bundle(parsed.font_configs),
            "module_resolver": build_runtime_module_resolver_config(),
        }

    def _build_preview_modules(self, parsed: ParsedProjectTemplatePackage) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
        """构建模板包预览使用的模块元数据和源码列表。"""

        modules_metadata: dict[str, dict[str, str]] = {}
        modules_by_path: dict[str, dict[str, str]] = {}
        route_page_codes = self._collect_route_page_codes(parsed.routes)
        for page in parsed.pages:
            ProjectArtifactBuilder.append_release_module(
                modules_metadata=modules_metadata,
                modules_data_by_path=modules_by_path,
                logical_path=f"src/views/{page.source_page_code}.vue",
                content=page.content,
                include_in_manifest=page.source_page_code in route_page_codes,
            )
        for component in parsed.components:
            ProjectArtifactBuilder.append_release_module(
                modules_metadata=modules_metadata,
                modules_data_by_path=modules_by_path,
                logical_path=ProjectArtifactBuilder.build_component_logical_path(
                    component.source_component_code,
                    component.source_version_no,
                ),
                content=component.content,
                include_in_manifest=False,
            )
        return modules_metadata, list(modules_by_path.values())

    @staticmethod
    def _build_preview_routes(routes_payload: dict[str, Any], pages: list[PackageTemplatePage]) -> dict[str, Any]:
        """把模板路由载荷转换为 Runtime 路由配置。"""

        page_title_by_code = {
            page.source_page_code: str(page.metadata.get("title") or page.source_page_code)
            for page in pages
        }

        def convert(route_item: dict[str, Any]) -> dict[str, Any]:
            route_type = str(route_item.get("route_type") or ProjectRouteType.PAGE.value)
            route = str(route_item.get("route") or "").strip()
            if route_type == ProjectRouteType.GROUP.value:
                return {
                    "route": route,
                    "meta": {
                        "title": str(route_item.get("group_title") or route).strip(),
                        "order": int(route_item.get("order") or 0),
                        "hidden": bool(route_item.get("hidden", False)),
                    },
                    "children": [convert(child) for child in route_item.get("children", []) if isinstance(child, dict)],
                }
            source_page_code = str(route_item.get("source_page_code") or "").strip()
            return {
                "route": route,
                "component": f"@/views/{source_page_code}.vue",
                "meta": {
                    "title": page_title_by_code.get(source_page_code, source_page_code),
                    "order": int(route_item.get("order") or 0),
                    "hidden": bool(route_item.get("hidden", False)),
                },
            }

        return {"routes": [convert(item) for item in routes_payload.get("routes", []) if isinstance(item, dict)]}

    @staticmethod
    def _resolve_preview_entry(parsed: ParsedProjectTemplatePackage) -> PreviewEntryDescriptor:
        """解析模板预览入口，优先使用路由首项。"""

        def first_route(items: list[Any], prefix: str = "") -> str | None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                route = str(item.get("route") or "").strip()
                if str(item.get("route_type") or "") == ProjectRouteType.GROUP.value:
                    child = first_route(item.get("children", []), f"{prefix}/{route}".strip("/"))
                    if child:
                        return child
                    continue
                if route:
                    return f"/{prefix}/{route}".replace("//", "/")
            return None

        route = first_route(parsed.routes.get("routes", []))
        if route:
            return PreviewEntryDescriptor(entry_type="route", route=route)
        first_page = parsed.pages[0] if parsed.pages else None
        return PreviewEntryDescriptor(
            entry_type="module",
            module_path=f"src/views/{first_page.source_page_code}.vue" if first_page else "src/views/template.vue",
        )

    @staticmethod
    def _build_package_asset_mapping(assets: list[PackageAsset]) -> dict[str, str]:
        """构建模板预览 manifest 的资源 name 到 hash 映射。"""

        return {
            str(asset.metadata.get("name") or "").strip(): str(asset.metadata.get("file_hash") or "").strip()
            for asset in assets
            if str(asset.metadata.get("name") or "").strip() and str(asset.metadata.get("file_hash") or "").strip()
        }

    @staticmethod
    def _build_package_asset_metadata(assets: list[PackageAsset]) -> dict[str, dict[str, object]]:
        """构建模板预览 manifest 的资源渲染元数据。"""

        result: dict[str, dict[str, object]] = {}
        for asset in assets:
            name = str(asset.metadata.get("name") or "").strip()
            asset_type = str(asset.metadata.get("asset_type") or "").strip()
            if not name or not asset_type:
                continue
            metadata: dict[str, object] = {
                "file_hash": str(asset.metadata.get("file_hash") or "").strip(),
                "original_name": str(asset.metadata.get("original_name") or "").strip(),
                "asset_role": resolve_asset_role(asset_type).value,
                "render_type": asset_type,
                "content_type": str(asset.metadata.get("content_type") or "").strip(),
            }
            ratio = AssetRenderMetadataService.summarize_metadata(asset.metadata.get("render_metadata"))
            for key in ("approx_aspect_ratio", "approx_aspect_ratio_value", "aspect_ratio_source"):
                if ratio.get(key) is not None:
                    metadata[key] = ratio[key]
            result[name] = metadata
        return result

    @staticmethod
    def _build_page_config(project_payload: dict[str, Any]) -> dict[str, Any]:
        """从项目载荷构建 Runtime app.page 配置。"""

        return {
            "width": int(project_payload.get("page_width") or 1920),
            "height": int(project_payload.get("page_height") or 1080),
            "baseFontSize": str(project_payload.get("base_font_size") or "20px"),
            "iconDefaultStrokeWidth": int(project_payload.get("icon_default_stroke_width") or 2),
        }

    @staticmethod
    def _parse_theme_config(theme_config_yaml: object) -> dict[str, Any]:
        """解析项目主题 YAML；失败时回退为空主题配置。"""

        import yaml

        try:
            value = yaml.safe_load(str(theme_config_yaml or "themes: {}")) or {}
        except yaml.YAMLError:
            return {"themes": {}}
        return value if isinstance(value, dict) else {"themes": {}}

    @staticmethod
    def _build_preview_font_bundle(font_configs: list[dict[str, Any]]) -> dict[str, Any]:
        """构建预览所需字体配置包。"""

        items = {}
        for item in font_configs:
            asset_name = str(item.get("asset_name") or "").strip()
            if not asset_name:
                continue
            items[asset_name] = {
                "asset_name": asset_name,
                "font_family": str(item.get("font_family") or "").strip(),
                "font_format": str(item.get("font_format") or "").strip(),
                "font_weight": str(item.get("font_weight") or "400").strip(),
                "font_style": str(item.get("font_style") or "normal").strip(),
                "font_display": str(item.get("font_display") or "swap").strip(),
            }
        return {"items": items}

    @staticmethod
    def _validate_template_project_payload(project: dict[str, Any], errors: list[str]) -> None:
        """校验模板包项目载荷的最低字段。"""

        required = ["name", "page_width", "page_height", "base_font_size", "theme_config_yaml"]
        missing = [field for field in required if project.get(field) in (None, "")]
        if missing:
            errors.append(f"project/project.json 缺少字段：{', '.join(missing)}。")

    def _validate_template_pages(
        self,
        pages: list[PackageTemplatePage],
        routes: dict[str, Any],
        errors: list[str],
    ) -> list[ProjectTemplatePackagePageSummary]:
        """校验模板包页面和路由引用。"""

        seen: set[str] = set()
        summaries: list[ProjectTemplatePackagePageSummary] = []
        for page in pages:
            if not page.source_page_code:
                errors.append("页面缺少 source_page_code。")
                continue
            if page.source_page_code in seen:
                errors.append(f"导入文件内存在重复页面：{page.source_page_code}。")
            seen.add(page.source_page_code)
            self._validate_page_imports(page, {item.source_page_code for item in pages}, errors)
            try:
                file_type = PageFileType(str(page.metadata.get("file_type") or PageFileType.VUE.value))
            except ValueError:
                errors.append(f"页面 {page.source_page_code} 的 file_type 不受支持。")
                file_type = PageFileType.VUE
            summaries.append(
                ProjectTemplatePackagePageSummary(
                    source_page_code=page.source_page_code,
                    title=str(page.metadata.get("title") or page.source_page_code),
                    summary=page.metadata.get("summary"),
                    file_type=file_type,
                )
            )
        route_page_codes = self._collect_route_page_codes(routes)
        missing_route_pages = [code for code in route_page_codes if code not in seen]
        if missing_route_pages:
            errors.append("导入项目路由引用的页面不在文件内：" + ", ".join(missing_route_pages))
        self._validate_template_routes(routes, errors)
        return summaries

    def _validate_template_routes(self, routes: dict[str, Any], errors: list[str]) -> None:
        """校验模板路由树中的路由片段合法性。"""

        def visit(items: list[Any]) -> None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                route = str(item.get("route") or "").strip()
                try:
                    ProjectRouteService._ensure_valid_route_segment(route, source_label="导入项目路由")
                except AppException as exc:
                    errors.append(str(exc.detail))
                if str(item.get("route_type") or "") == ProjectRouteType.GROUP.value:
                    visit(item.get("children", []))

        visit(routes.get("routes", []))

    def _validate_page_imports(self, page: PackageTemplatePage, package_page_codes: set[str], errors: list[str]) -> None:
        """校验页面源码中的页面模块引用仍在模板包闭包内。"""

        for match in re.finditer(r"['\"](?:@/views|src/views)/([^'\"]+?)\.vue['\"]", page.content):
            source_code = match.group(1).split("/")[-1]
            if source_code not in package_page_codes:
                errors.append(f"页面 {page.source_page_code} 引用的页面模块不在导入项目内：{source_code}。")

    def _validate_page_component_refs(
        self,
        pages: list[PackageTemplatePage],
        components: list[PackageComponent],
        errors: list[str],
    ) -> None:
        """校验页面源码引用的工作空间组件必须随模板包携带。"""

        component_refs = {
            (component.source_component_code, component.source_version_no)
            for component in components
        }
        missing: list[str] = []
        for page in pages:
            for ref in self._collect_component_refs_from_text(page.content):
                if ref not in component_refs:
                    missing.append(f"{ref[0]} v{ref[1]}")
        if missing:
            errors.append("页面引用的组件不在导入项目内：" + ", ".join(self._deduplicate_names(missing)))

    async def _validate_project_theme_reference(
        self,
        workspace_id: int,
        parsed: ParsedProjectTemplatePackage,
        errors: list[str],
    ) -> None:
        """校验项目 theme_key 在模板包或目标工作空间内可解析。"""

        theme_key = str(parsed.project.get("theme_key") or "").strip()
        if not theme_key:
            return
        package_theme_keys = {
            str(theme.payload.get("key") or "").strip()
            for theme in parsed.themes
            if str(theme.payload.get("key") or "").strip()
        }
        if theme_key in package_theme_keys:
            return
        existing_theme_id = await self.session.scalar(
            select(WorkspaceTheme.id)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.key == theme_key)
            .where(WorkspaceTheme.status == RecordStatus.ACTIVE.value)
        )
        if existing_theme_id is None:
            errors.append(f"项目引用的主题 {theme_key} 不在导入项目或目标工作空间中。")

    @staticmethod
    def _validate_template_screenshots(
        screenshots: dict[str, Any],
        pages: list[PackageTemplatePage],
        errors: list[str],
    ) -> ProjectTemplateScreenshotSummary:
        """校验截图清单结构并生成摘要。"""

        page_codes = {page.source_page_code for page in pages}
        cover_payload = screenshots.get("cover") if isinstance(screenshots.get("cover"), dict) else None
        cover = None
        if cover_payload is not None:
            cover = ProjectTemplateScreenshotItem(
                path=str(cover_payload.get("path") or ""),
                width=int(cover_payload.get("width") or 0),
                height=int(cover_payload.get("height") or 0),
                source_page_code=cover_payload.get("source_page_code"),
                title=cover_payload.get("title"),
                order=cover_payload.get("order"),
            )
        page_items: list[ProjectTemplateScreenshotItem] = []
        for item in screenshots.get("pages", []):
            if not isinstance(item, dict):
                continue
            source_page_code = str(item.get("source_page_code") or "").strip()
            if source_page_code and source_page_code not in page_codes:
                errors.append(f"截图引用的页面不在导入项目内：{source_page_code}。")
            page_items.append(
                ProjectTemplateScreenshotItem(
                    path=str(item.get("path") or ""),
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    source_page_code=source_page_code or None,
                    title=item.get("title"),
                    order=item.get("order"),
                )
            )
        return ProjectTemplateScreenshotSummary(cover=cover, pages=page_items)

    @staticmethod
    def _collect_route_page_codes(routes_payload: dict[str, Any]) -> list[str]:
        """递归收集模板路由引用的 source_page_code。"""

        result: list[str] = []

        def visit(items: list[Any]) -> None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("route_type") or "") == ProjectRouteType.GROUP.value:
                    visit(item.get("children", []))
                    continue
                source_page_code = str(item.get("source_page_code") or "").strip()
                if source_page_code:
                    result.append(source_page_code)

        visit(routes_payload.get("routes", []))
        return ProjectTemplatePackageService._deduplicate_names(result)

    async def _collect_project_themes(self, project: Project) -> list[WorkspaceTheme]:
        """收集项目主题 key 对应的主题库记录。"""

        theme_key = str(project.theme_key or "").strip()
        if not theme_key:
            return []
        theme = await self.session.scalar(
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == project.workspace_id)
            .where(WorkspaceTheme.key == theme_key)
            .where(WorkspaceTheme.deleted_at.is_(None))
        )
        return [theme] if theme is not None else []

    async def _collect_theme_dependencies(
        self,
        workspace_id: int,
        themes: list[WorkspaceTheme],
    ) -> tuple[list[WorkspaceAsset], list[WorkspaceFontConfig]]:
        """收集主题引用的资源和字体配置。"""

        assets_by_id: dict[int, WorkspaceAsset] = {}
        fonts_by_id: dict[int, WorkspaceFontConfig] = {}
        for theme in themes:
            for asset_id in [theme.logo_asset_id, theme.invert_logo_asset_id, theme.project_icon_asset_id]:
                if asset_id is None:
                    continue
                asset = await self.session.scalar(select(WorkspaceAsset).where(WorkspaceAsset.workspace_id == workspace_id, WorkspaceAsset.id == asset_id))
                if asset is not None:
                    assets_by_id[asset.id] = asset
            for font_id in [theme.heading_font_id, theme.body_font_id, theme.code_font_id]:
                if font_id is None:
                    continue
                font = await self.session.scalar(select(WorkspaceFontConfig).where(WorkspaceFontConfig.workspace_id == workspace_id, WorkspaceFontConfig.id == font_id))
                if font is not None:
                    fonts_by_id[font.id] = font
                    asset = await self.session.scalar(select(WorkspaceAsset).where(WorkspaceAsset.workspace_id == workspace_id, WorkspaceAsset.id == font.asset_id))
                    if asset is not None:
                        assets_by_id[asset.id] = asset
        return list(assets_by_id.values()), list(fonts_by_id.values())

    @staticmethod
    def _collect_page_asset_references(pages: list[Page]) -> tuple[list[str], list[str]]:
        """从页面源码中收集静态资源名和动态资源提示。"""

        asset_names: list[str] = []
        dynamic_modules: list[str] = []
        for page in pages:
            result = ResourceReferenceParser.collect_vue_asset_references(page.page_content)
            asset_names.extend(result.asset_names)
            if result.has_dynamic:
                dynamic_modules.append(f"src/views/{page.code}.{page.file_type}")
        return ProjectTemplatePackageService._deduplicate_names(asset_names), dynamic_modules

    async def _collect_project_config_asset_names(self, project: Project) -> list[str]:
        """从项目运行时配置中收集资源名。"""

        theme_config = await self.project_config_service.resolve_runtime_theme_config(project)
        app_config = await self.project_config_service.build_runtime_app_dict(project, theme_config=theme_config)
        icon_config = await self.project_config_service.runtime_icon_service.build_project_icon_config_from_modules(
            workspace_id=project.workspace_id,
            project_icon_name=self.project_config_service.resolve_project_icon_name_from_theme_config(theme_config),
            modules_data=[{"logical_path": f"src/views/{page.code}.{page.file_type}", "content": page.page_content} for page in await self._list_project_pages(project.id)],
        )
        font_bundle = await WorkspaceFontService(self.session).build_font_bundle_for_project(project)
        return ProjectArtifactBuilder.collect_config_asset_names(
            {
                "app": app_config,
                "themes": theme_config,
                "icons": icon_config,
                "fonts": font_bundle.model_dump(),
            }
        )

    async def _collect_project_suggested_asset_names(self, project_id: int) -> list[str]:
        """读取项目建议资源的逻辑名。"""

        result = await self.session.execute(
            select(WorkspaceAsset.name)
            .join(ProjectSuggestedReferenceAsset, ProjectSuggestedReferenceAsset.asset_id == WorkspaceAsset.id)
            .where(ProjectSuggestedReferenceAsset.project_id == project_id)
            .order_by(ProjectSuggestedReferenceAsset.sort_order.asc(), ProjectSuggestedReferenceAsset.id.asc())
        )
        return [str(item or "").strip() for item in result.scalars().all() if str(item or "").strip()]

    async def _collect_project_suggested_component_payloads(self, project_id: int) -> list[dict[str, Any]]:
        """读取项目建议组件并转为模板包源组件引用。"""

        result = await self.session.execute(
            select(WorkspaceComponent)
            .join(ProjectSuggestedComponent, ProjectSuggestedComponent.component_id == WorkspaceComponent.id)
            .where(ProjectSuggestedComponent.project_id == project_id)
            .order_by(ProjectSuggestedComponent.sort_order.asc(), ProjectSuggestedComponent.id.asc())
        )
        return [
            {
                "source_component_code": component.code,
                "source_version_no": component.current_version_no,
                "name": component.name,
                "import_name": component.import_name,
            }
            for component in result.scalars().all()
            if component.current_version_no > 0
        ]

    async def _collect_project_suggested_component_refs(self, project_id: int) -> list[tuple[str, int]]:
        """读取项目建议组件的当前发布版本，作为模板导出根组件。"""

        result = await self.session.execute(
            select(WorkspaceComponent)
            .join(ProjectSuggestedComponent, ProjectSuggestedComponent.component_id == WorkspaceComponent.id)
            .where(ProjectSuggestedComponent.project_id == project_id)
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .order_by(ProjectSuggestedComponent.sort_order.asc(), ProjectSuggestedComponent.id.asc())
        )
        return [
            (component.code, component.current_version_no)
            for component in result.scalars().all()
            if component.current_version_no > 0
        ]

    async def _list_workspace_assets_by_name(self, workspace_id: int) -> dict[str, WorkspaceAsset]:
        """读取工作空间可导出的根资源并按 name 建索引。"""

        result = await self.session.scalars(
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.source_asset_id.is_(None))
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
        )
        return {asset.name: asset for asset in result.all()}

    async def _list_project_pages(self, project_id: int) -> list[Page]:
        """读取项目下全部启用页面。"""

        result = await self.session.scalars(
            select(Page)
            .where(Page.project_id == project_id)
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(Page.deleted_at.is_(None))
            .order_by(Page.created_at.asc(), Page.id.asc())
        )
        return list(result.all())

    async def _get_active_project_or_raise(self, project_id: int) -> Project:
        """读取启用项目，不存在时抛出业务错误。"""

        project = await self.project_repository.get_by_id(project_id)
        if project is None or project.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在或未启用。")
        return project

    async def _build_theme_payload(self, theme: WorkspaceTheme) -> dict[str, Any]:
        """构建主题离线载荷。"""

        logo_asset, invert_logo_asset, project_icon_asset, heading_font, body_font, code_font = await WorkspaceThemeService(self.session)._load_theme_relations(theme)
        return {
            "key": theme.key,
            "name": theme.name,
            "description": theme.description,
            "logo_asset_name": logo_asset.name if logo_asset is not None else None,
            "invert_logo_asset_name": invert_logo_asset.name if invert_logo_asset is not None else None,
            "project_icon_asset_name": project_icon_asset.name if project_icon_asset is not None else None,
            "logo_path": logo_asset.name if logo_asset is not None else theme.logo_path,
            "invert_logo_path": invert_logo_asset.name if invert_logo_asset is not None else theme.invert_logo_path,
            "project_icon_name": project_icon_asset.name if project_icon_asset is not None else theme.project_icon_name,
            "heading_font_asset_name": heading_font.asset_name if heading_font is not None else None,
            "body_font_asset_name": body_font.asset_name if body_font is not None else None,
            "code_font_asset_name": code_font.asset_name if code_font is not None else None,
            "heading_font_label": heading_font.font_family if heading_font is not None else theme.heading_font_label,
            "body_font_label": body_font.font_family if body_font is not None else theme.body_font_label,
            "code_font_label": code_font.font_family if code_font is not None else theme.code_font_label,
            "palette": theme.palette,
        }

    @staticmethod
    def _build_asset_payload(asset: WorkspaceAsset) -> dict[str, Any]:
        """构建资源离线载荷。"""

        return {
            "name": asset.name,
            "original_name": asset.original_name,
            "asset_type": asset.asset_type,
            "content_type": asset.content_type,
            "file_size": asset.file_size,
            "file_hash": asset.file_hash,
            "description": asset.description,
            "tags": asset.tags or [],
            "analysis_metadata": asset.analysis_metadata,
            "render_metadata": asset.render_metadata,
        }

    @staticmethod
    def _build_font_payload(font_config: WorkspaceFontConfig) -> dict[str, Any]:
        """构建字体配置离线载荷。"""

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
    def _build_export_asset_summary(asset: WorkspaceAsset, source: str) -> ComponentShareExportAssetSummary:
        """构建导出资源摘要。"""

        return ComponentShareExportAssetSummary(
            name=asset.name,
            original_name=asset.original_name,
            asset_type=asset.asset_type,
            file_hash=asset.file_hash,
            source=source,
        )

    @staticmethod
    def _build_font_summary(font_config: WorkspaceFontConfig, *, action: str) -> Any:
        """构建字体摘要，复用组件包字体响应模型。"""

        from app.schemas.component import ComponentSharePackageFontSummary

        return ComponentSharePackageFontSummary(
            asset_name=font_config.asset_name,
            font_family=font_config.font_family,
            font_format=font_config.font_format,
            font_weight=font_config.font_weight,
            font_style=font_config.font_style,
            font_display=font_config.font_display,
            status=font_config.status,
            action=action,
        )

    @staticmethod
    def _build_project_summary(project: Project) -> ProjectTemplatePackageProjectSummary:
        """构建项目摘要。"""

        return ProjectTemplatePackageProjectSummary(
            source_project_code=project.code,
            name=project.name,
            description=project.description,
            page_width=project.page_width,
            page_height=project.page_height,
            base_font_size=project.base_font_size,
            icon_default_stroke_width=project.icon_default_stroke_width,
            show_pdf_export_button=project.show_pdf_export_button,
            menu_mode=project.menu_mode,
            theme_key=project.theme_key,
            style_spec_markdown=project.style_spec_markdown,
        )

    @staticmethod
    def _build_project_summary_from_payload(payload: dict[str, Any]) -> ProjectTemplatePackageProjectSummary:
        """从模板包项目载荷构建摘要。"""

        return ProjectTemplatePackageProjectSummary(
            source_project_code=str(payload.get("source_project_code") or ""),
            name=str(payload.get("name") or "未命名模板项目"),
            description=payload.get("description"),
            page_width=int(payload.get("page_width") or 1920),
            page_height=int(payload.get("page_height") or 1080),
            base_font_size=str(payload.get("base_font_size") or "20px"),
            icon_default_stroke_width=int(payload.get("icon_default_stroke_width") or 2),
            show_pdf_export_button=bool(payload.get("show_pdf_export_button", True)),
            menu_mode=str(payload.get("menu_mode") or "preview"),
            theme_key=str(payload.get("theme_key") or "").strip() or None,
            style_spec_markdown=str(payload.get("style_spec_markdown") or ""),
        )

    @staticmethod
    def _build_page_summary(page: Page) -> ProjectTemplatePackagePageSummary:
        """构建页面摘要。"""

        return ProjectTemplatePackagePageSummary(
            source_page_code=page.code,
            title=page.title,
            summary=page.summary,
            file_type=PageFileType(str(page.file_type)),
        )

    @staticmethod
    def _resolve_cover_page(pages: list[Page], routes: list[ProjectRoute], cover_page_id: int | None) -> Page | None:
        """解析封面页面，优先使用用户指定，其次使用首个路由页。"""

        page_by_id = {page.id: page for page in pages}
        if cover_page_id is not None and cover_page_id in page_by_id:
            return page_by_id[cover_page_id]
        for route in ProjectRouteService._sort_routes(routes):
            if route.page_id in page_by_id:
                return page_by_id[route.page_id]
        return pages[0] if pages else None

    @staticmethod
    def _rewrite_page_module_imports(source: str, page_code_mapping: dict[str, str]) -> str:
        """重写页面源码中的 `@/views/<code>.vue` 和 `src/views/<code>.vue` 引用。"""

        result = source
        for old_code, new_code in page_code_mapping.items():
            result = result.replace(f"@/views/{old_code}.vue", f"@/views/{new_code}.vue")
            result = result.replace(f"src/views/{old_code}.vue", f"src/views/{new_code}.vue")
        return result

    async def _generate_page_code_mapping(self, pages: list[PackageTemplatePage]) -> dict[str, str]:
        """为包内所有页面预分配新页面编码，支持页面之间前后互相引用。"""

        if not pages:
            return {}
        first_code = await generate_code(self.session, Page, CODE_PREFIX_PAGE)
        prefix_length = len(CODE_PREFIX_PAGE) + 8
        sequence_text = first_code[prefix_length:]
        try:
            first_sequence = int(sequence_text)
        except ValueError:
            first_sequence = 1
        prefix = first_code[:prefix_length]
        return {
            page.source_page_code: f"{prefix}{first_sequence + index:03d}"
            for index, page in enumerate(pages)
        }

    @staticmethod
    def _collect_component_refs_from_text(source: str) -> list[tuple[str, int]]:
        """从源码文本中收集工作空间组件 import 引用。"""

        return [
            (match.group("component_code"), int(match.group("version_no")))
            for match in COMPONENT_IMPORT_PATTERN.finditer(source or "")
        ]

    @staticmethod
    def _deduplicate_component_refs(refs: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """按顺序去重组件引用。"""

        result: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            result.append(ref)
        return result

    @staticmethod
    def _deduplicate_names(values: list[str]) -> list[str]:
        """按顺序归一化字符串列表并去重。"""

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _deduplicate_assets(assets: list[WorkspaceAsset]) -> list[WorkspaceAsset]:
        """按资源 ID 去重。"""

        result: list[WorkspaceAsset] = []
        seen: set[int] = set()
        for asset in assets:
            if asset.id in seen:
                continue
            seen.add(asset.id)
            result.append(asset)
        return result

    @staticmethod
    def _deduplicate_font_configs(font_configs: list[WorkspaceFontConfig]) -> list[WorkspaceFontConfig]:
        """按字体配置 ID 去重。"""

        result: list[WorkspaceFontConfig] = []
        seen: set[int] = set()
        for item in font_configs:
            if item.id in seen:
                continue
            seen.add(item.id)
            result.append(item)
        return result

    @staticmethod
    def _slugify(value: str) -> str:
        """把模板名称转成外部模板库可用 slug。"""

        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
        return slug or "project-template"

    @staticmethod
    def _format_aspect_ratio(width: int, height: int) -> str:
        """格式化宽高比。"""

        def gcd(a: int, b: int) -> int:
            while b:
                a, b = b, a % b
            return max(a, 1)

        divisor = gcd(int(width or 1), int(height or 1))
        return f"{int(width / divisor)}:{int(height / divisor)}"

    @staticmethod
    def _build_export_filename(project_name: str) -> str:
        """生成模板包下载文件名。"""

        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "-", project_name).strip("-") or "project-template"
        return f"{safe_name}.wptemplate.zip"

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        """把输入值转为整数，失败时返回 None。"""

        try:
            return int(value)
        except (TypeError, ValueError):
            return None
