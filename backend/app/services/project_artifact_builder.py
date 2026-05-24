"""文件功能：构建项目级预览与整包构建共用的不可变 artifact 快照。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.runtime_module_policy import build_runtime_module_resolver_config
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.workspace import Project
from app.repositories.module_dependency_repository import (
    DEPENDENCY_KIND_COMPONENT,
    DEPENDENCY_KIND_PAGE_MODULE,
    ModuleDependencyRepository,
)
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.schemas.asset import resolve_asset_role
from app.schemas.project_app_config import ProjectAppPageConfig
from app.schemas.project import normalize_project_build_extra_assets_config
from app.schemas.release import PreviewEntryDescriptor
from app.services.component_dependency_service import ComponentDependencyService
from app.services.project_config_service import ProjectConfigService
from app.services.resource_reference_parser import ResourceReferenceParser
from app.services.project_route_service import ProjectRouteService
from app.services.runtime_icon_service import RuntimeIconService
from app.services.workspace_font_service import WorkspaceFontService

AssetDeliveryMode = Literal["public", "backend_cache"]
AssetSnapshotMode = Literal["all", "referenced"]


@dataclass(slots=True)
class ProjectArtifactSnapshot:
    """项目级 artifact 快照。"""

    project: Project
    preview_kind: Literal["project", "page"]
    entry_descriptor: PreviewEntryDescriptor
    page_config: ProjectAppPageConfig
    config_bundle: dict[str, object]
    asset_base_url: str
    asset_mapping: dict[str, str]
    asset_metadata: dict[str, dict[str, str]]
    modules_metadata: dict[str, dict[str, str]]
    modules_data: list[dict[str, str]]


@dataclass(slots=True, frozen=True)
class ProjectPageModuleOverride:
    """单页预览时对入口页面源码和依赖版本的临时覆盖。"""

    content: str
    page_version_id: int | None = None


@dataclass(slots=True, frozen=True)
class ProjectBuildAssetReferenceSummary:
    """项目构建资源引用摘要，区分自动引用和项目额外声明。"""

    automatic_asset_names: list[str]
    extra_asset_names: list[str]
    included_asset_names: list[str]
    dynamic_module_paths: list[str]


@dataclass(slots=True, frozen=True)
class _TransientPageDependency:
    """未落库页面候选源码解析出的临时依赖项。"""

    dependency_kind: str
    component_version_id: int | None = None
    runtime_module_path: str | None = None

    @classmethod
    def from_component(cls, item: object) -> "_TransientPageDependency":
        """从已解析组件依赖构造临时依赖项。"""

        return cls(
            dependency_kind=DEPENDENCY_KIND_COMPONENT,
            component_version_id=int(getattr(item, "component_version_id")),
        )


class ProjectArtifactBuilder:
    """按项目当前状态生成可复用的 artifact 快照。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_route_service = ProjectRouteService(session)
        self.project_config_service = ProjectConfigService(session)
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)
        self.module_dependency_repository = ModuleDependencyRepository(session)
        self.runtime_icon_service = RuntimeIconService(session)

    async def build_snapshot(
        self,
        *,
        project_id: int,
        entry_descriptor: PreviewEntryDescriptor | None = None,
        page_module_overrides: dict[str, ProjectPageModuleOverride] | None = None,
        transient_pages: list[Page] | None = None,
        asset_delivery_mode: AssetDeliveryMode = "public",
        asset_snapshot_mode: AssetSnapshotMode = "all",
    ) -> ProjectArtifactSnapshot:
        """构建项目级预览/构建共用快照。"""

        settings = get_settings()
        project = await self.get_project_or_raise(project_id)
        runtime_route_config = await self.project_route_service.build_runtime_route_config(project.id)
        normalized_entry_descriptor = entry_descriptor or PreviewEntryDescriptor(
            entry_type="route",
            route=self.resolve_default_entry_route(runtime_route_config),
        )
        if normalized_entry_descriptor.entry_type == "route":
            normalized_entry_descriptor = PreviewEntryDescriptor(
                entry_type="route",
                route=self.validate_entry_route(runtime_route_config, normalized_entry_descriptor.route or ""),
            )
        theme_config = await self.project_config_service.resolve_runtime_theme_config(project)
        app_config = await self.project_config_service.build_runtime_app_dict(project, theme_config=theme_config)
        page_config = self.project_config_service.resolve_project_page_config(project)
        all_project_pages = self._merge_transient_pages(
            await self.list_project_pages(project.id),
            transient_pages,
        )
        standalone_entry_page = self.resolve_direct_entry_page(
            all_project_pages,
            normalized_entry_descriptor.module_path or "",
        )

        if normalized_entry_descriptor.entry_type == "module" and standalone_entry_page is None:
            raise AppException(
                status_code=404,
                code="PREVIEW_ENTRY_PAGE_NOT_FOUND",
                detail="单页面预览入口对应的页面不存在，无法生成预览快照。",
            )

        preview_kind: Literal["project", "page"] = (
            "page" if normalized_entry_descriptor.entry_type == "module" else "project"
        )
        route_component_paths = self.collect_runtime_route_component_paths(runtime_route_config)
        route_pages = [
            page for page in all_project_pages
            if f"@/views/{page.code}.{page.file_type}" in route_component_paths
        ]
        preview_root_pages = self.merge_preview_root_pages(route_pages, standalone_entry_page)
        manifest_page_paths = self.build_manifest_page_paths(route_pages, standalone_entry_page)
        modules_metadata, modules_data = await self.build_release_module_graph(
            preview_root_pages,
            manifest_page_paths=manifest_page_paths,
            page_module_overrides=page_module_overrides,
        )
        font_service = WorkspaceFontService(self.session)
        font_bundle = await font_service.build_font_bundle_for_project(
            project,
            explicit_asset_names=font_service.collect_declared_font_asset_names_from_modules(modules_data),
        )
        if normalized_entry_descriptor.entry_type == "module":
            icon_config = await self.runtime_icon_service.build_page_icon_config_from_modules(
                workspace_id=project.workspace_id,
                modules_data=modules_data,
            )
        else:
            icon_config = await self.runtime_icon_service.build_project_icon_config_from_modules(
                workspace_id=project.workspace_id,
                project_icon_name=self.project_config_service.resolve_project_icon_name_from_theme_config(theme_config),
                modules_data=modules_data,
            )

        config_bundle = {
            "app": app_config,
            "routes": runtime_route_config,
            "icons": icon_config,
            "themes": theme_config,
            "fonts": font_bundle.model_dump(),
            "module_resolver": build_runtime_module_resolver_config(),
        }

        required_asset_names: list[str] | None = None
        if asset_snapshot_mode == "referenced":
            required_asset_names = await self.collect_build_required_asset_names(
                workspace_id=project.workspace_id,
                modules_data=modules_data,
                config_bundle=config_bundle,
                extra_asset_names=normalize_project_build_extra_assets_config(
                    project.build_extra_assets_json
                ).asset_names,
            )
        asset_mapping, asset_metadata = await self.build_workspace_asset_snapshot(
            project.workspace_id,
            required_asset_names=required_asset_names,
        )
        asset_base_url = self.build_asset_base_url(
            settings.backend_public_base_url,
            project.workspace_id,
            asset_delivery_mode,
        )

        return ProjectArtifactSnapshot(
            project=project,
            preview_kind=preview_kind,
            entry_descriptor=normalized_entry_descriptor,
            page_config=page_config,
            config_bundle=config_bundle,
            asset_base_url=asset_base_url,
            asset_mapping=asset_mapping,
            asset_metadata=asset_metadata,
            modules_metadata=modules_metadata,
            modules_data=modules_data,
        )

    async def collect_project_build_asset_reference_summary(
        self,
        project_id: int,
    ) -> ProjectBuildAssetReferenceSummary:
        """收集项目构建资源引用摘要，不创建快照也不读取资源文件映射。"""

        project = await self.get_project_or_raise(project_id)
        runtime_route_config = await self.project_route_service.build_runtime_route_config(project.id)
        theme_config = await self.project_config_service.resolve_runtime_theme_config(project)
        app_config = await self.project_config_service.build_runtime_app_dict(project, theme_config=theme_config)
        all_project_pages = await self.list_project_pages(project.id)
        route_component_paths = self.collect_runtime_route_component_paths(runtime_route_config)
        route_pages = [
            page for page in all_project_pages
            if f"@/views/{page.code}.{page.file_type}" in route_component_paths
        ]
        manifest_page_paths = self.build_manifest_page_paths(route_pages, None)
        _, modules_data = await self.build_release_module_graph(
            route_pages,
            manifest_page_paths=manifest_page_paths,
        )
        font_service = WorkspaceFontService(self.session)
        font_bundle = await font_service.build_font_bundle_for_project(
            project,
            explicit_asset_names=font_service.collect_declared_font_asset_names_from_modules(modules_data),
        )
        icon_config = await self.runtime_icon_service.build_project_icon_config_from_modules(
            workspace_id=project.workspace_id,
            project_icon_name=self.project_config_service.resolve_project_icon_name_from_theme_config(theme_config),
            modules_data=modules_data,
        )
        config_bundle = {
            "app": app_config,
            "routes": runtime_route_config,
            "icons": icon_config,
            "themes": theme_config,
            "fonts": font_bundle.model_dump(),
            "module_resolver": build_runtime_module_resolver_config(),
        }

        static_module_asset_names, dynamic_module_paths = self.collect_module_asset_references(modules_data)
        config_asset_names = self.collect_config_asset_names(config_bundle)
        automatic_asset_names = self.normalize_asset_names([*static_module_asset_names, *config_asset_names])
        extra_asset_names = self.normalize_asset_names(
            normalize_project_build_extra_assets_config(project.build_extra_assets_json).asset_names
        )
        return ProjectBuildAssetReferenceSummary(
            automatic_asset_names=automatic_asset_names,
            extra_asset_names=extra_asset_names,
            included_asset_names=self.normalize_asset_names([*automatic_asset_names, *extra_asset_names]),
            dynamic_module_paths=dynamic_module_paths,
        )

    @staticmethod
    def build_asset_base_url(backend_public_base_url: str, workspace_id: int, mode: AssetDeliveryMode = "public") -> str:
        """根据资源下发模式构建 manifest 中的资源根地址。"""

        public_base = backend_public_base_url.rstrip("/")
        if mode == "backend_cache":
            return f"{public_base}/public/cached-assets/{workspace_id}"
        return f"{public_base}/public/assets/{workspace_id}"

    async def get_project_or_raise(self, project_id: int) -> Project:
        """按主键读取项目；若不存在或已归档则抛出标准错误。"""

        stmt = select(Project).where(Project.id == project_id, Project.status == RecordStatus.ACTIVE.value)
        project = (await self.session.execute(stmt)).scalar_one_or_none()
        if project is None:
            raise AppException(404, "PROJECT_NOT_FOUND", "当前项目不存在或已归档")
        return project

    async def list_project_pages(self, project_id: int) -> list[Page]:
        """读取项目下所有活动页面，为模块图构建提供入口候选。"""

        stmt = select(Page).where(Page.project_id == project_id, Page.status == RecordStatus.ACTIVE.value)
        return (await self.session.execute(stmt)).scalars().all()

    async def build_workspace_asset_snapshot(
        self,
        workspace_id: int,
        *,
        required_asset_names: Iterable[str] | None = None,
    ) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        """构建 manifest 资源映射与构建期资源元信息。"""

        normalized_required_names = self.normalize_asset_names(required_asset_names or [])
        if required_asset_names is not None and not normalized_required_names:
            return {}, {}

        stmt = (
            select(WorkspaceAsset)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.source_asset_id.is_(None))
            .order_by(WorkspaceAsset.created_at.desc(), WorkspaceAsset.id.desc())
        )
        if required_asset_names is not None:
            stmt = stmt.where(WorkspaceAsset.name.in_(normalized_required_names))
        workspace_assets = (await self.session.execute(stmt)).scalars().all()

        asset_mapping: dict[str, str] = {}
        asset_metadata: dict[str, dict[str, str]] = {}
        for asset in workspace_assets:
            asset_name = str(asset.name or "").strip()
            file_hash = str(asset.file_hash or "").strip()
            original_name = str(asset.original_name or "").strip()
            if not asset_name or not file_hash:
                continue
            asset_mapping.setdefault(asset_name, file_hash)
            asset_metadata.setdefault(
                asset_name,
                {
                    "file_hash": file_hash,
                    "original_name": original_name,
                    "asset_role": resolve_asset_role(asset.asset_type).value,
                    "render_type": str(asset.asset_type or "").strip(),
                    "content_type": str(asset.content_type or "").strip(),
                },
            )

        if required_asset_names is not None:
            missing_names = [name for name in normalized_required_names if name not in asset_mapping]
            if missing_names:
                raise AppException(
                    status_code=409,
                    code="PROJECT_BUILD_ASSET_MISSING",
                    detail=f"构建所需资源不存在或不是根资源：{', '.join(missing_names)}。",
                    data={
                        "missing_asset_names": missing_names,
                        "required_asset_names": normalized_required_names,
                    },
                )
            asset_mapping = {name: asset_mapping[name] for name in normalized_required_names if name in asset_mapping}
            asset_metadata = {name: asset_metadata[name] for name in normalized_required_names if name in asset_metadata}

        return asset_mapping, asset_metadata

    async def collect_build_required_asset_names(
        self,
        *,
        workspace_id: int,
        modules_data: list[dict[str, str]],
        config_bundle: dict[str, object],
        extra_asset_names: Iterable[str],
    ) -> list[str]:
        """收集整包构建必须物化的资源名，避免默认打包全量工作空间资源。"""

        static_module_asset_names, dynamic_module_paths = self.collect_module_asset_references(modules_data)
        config_asset_names = self.collect_config_asset_names(config_bundle)
        normalized_extra_names = self.normalize_asset_names(extra_asset_names)
        required_asset_names = self.normalize_asset_names(
            [
                *static_module_asset_names,
                *config_asset_names,
                *normalized_extra_names,
            ]
        )

        if dynamic_module_paths and not normalized_extra_names:
            candidate_asset_names = await self.list_workspace_build_asset_names(
                workspace_id,
                exclude_names=required_asset_names,
            )
            raise AppException(
                status_code=409,
                code="PROJECT_BUILD_DYNAMIC_ASSET_REFERENCE",
                detail=(
                    "构建源码中存在无法静态解析的资源名。请在项目构建额外资源 JSON 中补充这些动态资源后重试。"
                ),
                data={
                    "dynamic_module_paths": dynamic_module_paths,
                    "candidate_asset_names": candidate_asset_names,
                    "current_extra_asset_names": normalized_extra_names,
                },
            )

        return required_asset_names

    async def list_workspace_build_asset_names(
        self,
        workspace_id: int,
        *,
        exclude_names: Iterable[str],
    ) -> list[str]:
        """读取可加入构建额外资源 JSON 的工作空间根资源名。"""

        excluded = set(self.normalize_asset_names(exclude_names))
        stmt = (
            select(WorkspaceAsset.name)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.source_asset_id.is_(None))
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
            .order_by(WorkspaceAsset.updated_at.desc(), WorkspaceAsset.id.desc())
            .limit(200)
        )
        names = [str(item or "").strip() for item in (await self.session.execute(stmt)).scalars().all()]
        return [name for name in names if name and name not in excluded]

    @classmethod
    def collect_module_asset_references(cls, modules_data: list[dict[str, str]]) -> tuple[list[str], list[str]]:
        """从页面和组件源码快照中收集静态资源名，并记录动态资源模块。"""

        asset_names: list[str] = []
        dynamic_module_paths: list[str] = []
        for module_item in modules_data:
            logical_path = str(module_item.get("logical_path") or "").strip()
            source_text = str(module_item.get("content") or "")
            result = ResourceReferenceParser.collect_vue_asset_references(source_text)
            asset_names.extend(result.asset_names)
            if result.has_dynamic:
                dynamic_module_paths.append(logical_path or "<unknown>")
        return cls.normalize_asset_names(asset_names), cls.normalize_asset_names(dynamic_module_paths)

    @classmethod
    def collect_config_asset_names(cls, config_bundle: dict[str, object]) -> list[str]:
        """从主题、图标和字体配置中收集必须进入构建产物的资源名。"""

        asset_names: list[str] = []
        themes_config = config_bundle.get("themes")
        if isinstance(themes_config, dict):
            themes = themes_config.get("themes")
            if isinstance(themes, dict):
                for theme_item in themes.values():
                    if not isinstance(theme_item, dict):
                        continue
                    cls.append_asset_name(asset_names, theme_item.get("logo"))
                    cls.append_asset_name(asset_names, theme_item.get("invertLogo"))

        icons_config = config_bundle.get("icons")
        if isinstance(icons_config, dict):
            static_icons = icons_config.get("static_icons")
            if isinstance(static_icons, list):
                for icon_item in static_icons:
                    if isinstance(icon_item, dict):
                        cls.append_asset_name(asset_names, icon_item.get("src"))

        fonts_config = config_bundle.get("fonts")
        if isinstance(fonts_config, dict):
            font_items = fonts_config.get("items")
            if isinstance(font_items, dict):
                for font_item in font_items.values():
                    if isinstance(font_item, dict):
                        cls.append_asset_name(asset_names, font_item.get("asset_name"))

        return cls.normalize_asset_names(asset_names)

    @staticmethod
    def append_asset_name(target: list[str], raw_value: object) -> None:
        """把单个资源名追加到目标列表，URL 和空值会被忽略。"""

        normalized = str(raw_value or "").strip().replace("\\", "/").lstrip("./")
        if not normalized or re.match(r"^https?://", normalized, flags=re.IGNORECASE):
            return
        target.append(normalized)

    @staticmethod
    def normalize_asset_names(values: Iterable[str]) -> list[str]:
        """按顺序归一化资源名并去重。"""

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip().replace("\\", "/").lstrip("./")
            if not normalized or re.match(r"^https?://", normalized, flags=re.IGNORECASE):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    async def build_release_module_graph(
        self,
        pages: list[Page],
        *,
        manifest_page_paths: set[str] | None = None,
        page_module_overrides: dict[str, ProjectPageModuleOverride] | None = None,
    ) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
        """按页面入口递归收集页面与组件版本的完整模块图。"""

        modules_metadata: dict[str, dict[str, str]] = {}
        modules_data_by_path: dict[str, dict[str, str]] = {}
        resolved_page_module_overrides = page_module_overrides or {}
        all_project_pages = self._merge_transient_pages(
            await self.list_project_pages(pages[0].project_id) if pages else [],
            pages,
        )
        page_map = {
            f"src/views/{page.code}.{page.file_type}": page
            for page in all_project_pages
        }
        queued_page_paths: list[str] = []
        page_manifest_includes: dict[str, bool] = {}
        queued_component_version_ids: list[int] = []
        visited_page_paths: set[str] = set()
        visited_component_version_ids: set[int] = set()

        for page in pages:
            logical_path = f"src/views/{page.code}.{page.file_type}"
            queued_page_paths.append(logical_path)
            page_manifest_includes[logical_path] = manifest_page_paths is None or logical_path in manifest_page_paths

        while queued_page_paths:
            logical_path = queued_page_paths.pop(0)
            if logical_path in visited_page_paths:
                continue
            visited_page_paths.add(logical_path)

            page = page_map.get(logical_path)
            if page is None:
                raise AppException(
                    status_code=409,
                    code="PREVIEW_PAGE_MODULE_MISSING",
                    detail=f"预览依赖的页面模块不存在：{logical_path}。",
                )

            page_override = resolved_page_module_overrides.get(logical_path)
            self.append_release_module(
                modules_metadata=modules_metadata,
                modules_data_by_path=modules_data_by_path,
                logical_path=logical_path,
                content=page_override.content if page_override is not None else page.page_content,
                include_in_manifest=page_manifest_includes.get(logical_path, True),
            )
            dependency_page_version_id = page_override.page_version_id if page_override is not None else None
            if dependency_page_version_id is not None:
                dependency_items = await self.module_dependency_repository.list_page_version_dependencies(
                    dependency_page_version_id
                )
            elif page_override is not None:
                dependency_items = await self._build_transient_page_dependency_items(
                    workspace_id=page.workspace_id,
                    source_label=f"页面 {page.code}",
                    importer_module_path=logical_path,
                    page_content=page_override.content,
                )
            else:
                page_version = await self.get_page_current_version(page)
                if page_version is None:
                    continue
                dependency_items = await self.module_dependency_repository.list_page_version_dependencies(page_version.id)

            if not dependency_items:
                continue

            for item in dependency_items:
                if item.dependency_kind == DEPENDENCY_KIND_COMPONENT and item.component_version_id is not None:
                    queued_component_version_ids.append(item.component_version_id)
                    continue
                if item.dependency_kind == DEPENDENCY_KIND_PAGE_MODULE and item.runtime_module_path:
                    dependency_path = str(item.runtime_module_path).strip()
                    if not dependency_path:
                        continue
                    queued_page_paths.append(dependency_path)
                    page_manifest_includes.setdefault(dependency_path, True)

        while queued_component_version_ids:
            component_version_id = queued_component_version_ids.pop(0)
            if component_version_id in visited_component_version_ids:
                continue
            visited_component_version_ids.add(component_version_id)

            component_version = await self.component_version_repository.get_by_id(component_version_id)
            if component_version is None:
                raise AppException(
                    status_code=409,
                    code="PREVIEW_COMPONENT_VERSION_MISSING",
                    detail="预览依赖的组件版本不存在，无法生成模块快照。",
                )

            component = await self.component_repository.get_by_id(component_version.component_id)
            if component is None:
                raise AppException(
                    status_code=409,
                    code="PREVIEW_COMPONENT_MISSING",
                    detail="预览依赖的组件不存在，无法生成模块快照。",
                )

            logical_path = self.build_component_logical_path(component.code, component_version.version_no)
            self.append_release_module(
                modules_metadata=modules_metadata,
                modules_data_by_path=modules_data_by_path,
                logical_path=logical_path,
                content=component_version.content,
                include_in_manifest=True,
            )

            dependency_items = await self.module_dependency_repository.list_component_version_dependencies(component_version.id)
            for item in dependency_items:
                if item.dependency_kind != DEPENDENCY_KIND_COMPONENT or item.dependency_component_version_id is None:
                    continue
                queued_component_version_ids.append(item.dependency_component_version_id)

        return modules_metadata, list(modules_data_by_path.values())

    async def _build_transient_page_dependency_items(
        self,
        *,
        workspace_id: int | None,
        source_label: str,
        importer_module_path: str,
        page_content: str,
    ) -> list[object]:
        """为未落库页面候选源码即时解析依赖，供代码检查和草稿预览构建完整模块图。"""

        dependency_service = ComponentDependencyService(self.session)
        parsed_dependencies = dependency_service.parse_dependencies(
            page_content,
            source_label=source_label,
            importer_module_path=importer_module_path,
            allow_page_module_imports=True,
        )
        component_dependencies = await dependency_service.resolve_component_dependencies(
            workspace_id=workspace_id,
            component_refs=parsed_dependencies.component_imports,
            source_label=source_label,
        )
        dependency_items = [_TransientPageDependency.from_component(item) for item in component_dependencies]
        dependency_items.extend(
            _TransientPageDependency(
                dependency_kind=DEPENDENCY_KIND_PAGE_MODULE,
                runtime_module_path=path,
            )
            for path in parsed_dependencies.page_module_imports
        )
        return dependency_items

    async def get_page_current_version(self, page: Page) -> PageVersion | None:
        """读取页面当前版本快照，供模块图收集依赖索引。"""

        return await self.session.scalar(
            select(PageVersion)
            .where(PageVersion.page_id == page.id)
            .where(PageVersion.version_no == page.current_version_no)
        )

    @staticmethod
    def _merge_transient_pages(saved_pages: list[Page], transient_pages: list[Page] | None) -> list[Page]:
        """把未落库页面草稿合并进模块候选列表，供预览与代码检查解析入口。"""

        pages_by_path = {
            f"src/views/{page.code}.{page.file_type}": page
            for page in saved_pages
        }
        for page in transient_pages or []:
            pages_by_path.setdefault(f"src/views/{page.code}.{page.file_type}", page)
        return list(pages_by_path.values())

    @staticmethod
    def append_release_module(
        *,
        modules_metadata: dict[str, dict[str, str]],
        modules_data_by_path: dict[str, dict[str, str]],
        logical_path: str,
        content: str,
        include_in_manifest: bool,
    ) -> None:
        """将一个逻辑模块快照追加到 release_modules，并按需登记到 manifest。"""

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        modules_data_by_path.setdefault(
            logical_path,
            {
                "logical_path": logical_path,
                "content": content,
                "content_hash": content_hash,
            },
        )
        if include_in_manifest and logical_path not in modules_metadata:
            modules_metadata[logical_path] = {
                "path": logical_path,
                "hash": f"sha256:{content_hash[:8]}",
            }

    @staticmethod
    def build_component_logical_path(component_code: str, version_no: int) -> str:
        """将组件编码和版本号转为 Release 中的逻辑模块路径。"""

        return f"src/workspace-components/{component_code}/v/{version_no}.vue"

    @staticmethod
    def collect_runtime_route_component_paths(runtime_route_config: dict[str, list[dict[str, object]]]) -> set[str]:
        """收集运行时路由配置中实际引用的页面组件别名路径。"""

        component_paths: set[str] = set()
        for route_item in runtime_route_config.get("routes", []):
            component = str(route_item.get("component") or "").strip()
            if component:
                component_paths.add(component)
            for child in route_item.get("children", []) or []:
                child_component = str(child.get("component") or "").strip()
                if child_component:
                    component_paths.add(child_component)
        return component_paths

    @classmethod
    def resolve_direct_entry_page(cls, all_project_pages: list[Page], module_path: str) -> Page | None:
        """根据单页面预览入口解析目标页面；非页面模块入口时返回空。"""

        normalized_module_path = cls.normalize_direct_entry_module_path(module_path)
        if not normalized_module_path:
            return None

        for page in all_project_pages:
            logical_path = f"src/views/{page.code}.{page.file_type}"
            if logical_path == normalized_module_path:
                return page
        return None

    @staticmethod
    def normalize_direct_entry_module_path(module_path: str) -> str:
        """将单页面预览入口统一规范化为 `src/views/*.vue` 形式。"""

        normalized_module_path = str(module_path or "").strip().replace("\\", "/")
        if not normalized_module_path:
            return ""
        if normalized_module_path.startswith("@/"):
            normalized_module_path = normalized_module_path.replace("@/", "src/", 1)
        elif normalized_module_path.startswith("/src/"):
            normalized_module_path = normalized_module_path[1:]

        if re.fullmatch(r"src/views/[^/]+\.[A-Za-z0-9]+", normalized_module_path):
            return normalized_module_path
        return ""

    @staticmethod
    def merge_preview_root_pages(route_pages: list[Page], standalone_entry_page: Page | None) -> list[Page]:
        """合并路由页面与单页面预览入口，避免重复收集。"""

        merged_pages: list[Page] = []
        seen_page_ids: set[int] = set()
        for page in [*route_pages, standalone_entry_page]:
            if page is None or page.id in seen_page_ids:
                continue
            seen_page_ids.add(page.id)
            merged_pages.append(page)
        return merged_pages

    @staticmethod
    def build_manifest_page_paths(route_pages: list[Page], standalone_entry_page: Page | None) -> set[str]:
        """生成页面模块白名单；单页面预览入口页始终不进入 manifest。"""

        standalone_entry_path = ""
        if standalone_entry_page is not None:
            standalone_entry_path = f"src/views/{standalone_entry_page.code}.{standalone_entry_page.file_type}"

        return {
            f"src/views/{page.code}.{page.file_type}"
            for page in route_pages
            if f"src/views/{page.code}.{page.file_type}" != standalone_entry_path
        }

    @classmethod
    def validate_entry_route(cls, runtime_route_config: dict[str, list[dict[str, object]]], route: str) -> str:
        """校验整项目预览入口路由存在，并统一输出 Runtime 使用的绝对路径。"""

        normalized_route = cls.normalize_entry_route(route)
        if normalized_route not in cls.collect_runtime_route_paths(runtime_route_config):
            raise AppException(
                status_code=400,
                code="PREVIEW_ENTRY_ROUTE_NOT_FOUND",
                detail=f"整项目预览入口路由不存在：{normalized_route}。",
            )
        return normalized_route

    @staticmethod
    def normalize_entry_route(route: str) -> str:
        """将入口路由统一规范为以 `/` 开头且无重复分隔符的路径。"""

        normalized_route = str(route or "").strip().replace("\\", "/")
        if not normalized_route or normalized_route == "/":
            return "/"
        normalized_route = f"/{normalized_route.lstrip('/')}"
        return re.sub(r"/{2,}", "/", normalized_route)

    @classmethod
    def collect_runtime_route_paths(cls, runtime_route_config: dict[str, list[dict[str, object]]]) -> set[str]:
        """从 Runtime 路由配置中收集全部可作为项目预览入口的路径。"""

        result: set[str] = set()
        for route_item in runtime_route_config.get("routes", []) or []:
            cls._collect_runtime_route_paths_recursive(result, route_item, parent_path="")
        return result

    @classmethod
    def _collect_runtime_route_paths_recursive(
        cls,
        result: set[str],
        route_item: object,
        *,
        parent_path: str,
    ) -> None:
        """递归收集 Runtime 会注册的页面路径与分组重定向路径。"""

        if not isinstance(route_item, dict):
            return

        route_segment = str(route_item.get("route") or "").strip()
        children = route_item.get("children", []) or []
        normalized_current_path = cls._join_route_path(parent_path, route_segment)
        if children:
            if normalized_current_path and cls._has_visible_child_route(children):
                result.add(normalized_current_path)
            for child in children:
                cls._collect_runtime_route_paths_recursive(result, child, parent_path=normalized_current_path)
            return
        if normalized_current_path:
            result.add(normalized_current_path)

    @staticmethod
    def _has_visible_child_route(children: object) -> bool:
        """判断分组是否存在可作为父级重定向目标的可见子路由。"""

        if not isinstance(children, list):
            return False
        for child in children:
            if not isinstance(child, dict):
                continue
            route_segment = str(child.get("route") or "").strip()
            meta = child.get("meta") if isinstance(child.get("meta"), dict) else {}
            if route_segment and not bool(meta.get("hidden")):
                return True
        return False

    @staticmethod
    def _join_route_path(parent_path: str, route_segment: str) -> str:
        """拼接父子路由段并保证结果符合 Runtime 路径格式。"""

        normalized_segment = str(route_segment or "").strip().strip("/")
        if not normalized_segment:
            return parent_path or "/"
        if not parent_path or parent_path == "/":
            return f"/{normalized_segment}"
        return re.sub(r"/{2,}", "/", f"{parent_path.rstrip('/')}/{normalized_segment}")

    @staticmethod
    def resolve_default_entry_route(runtime_route_config: dict[str, list[dict[str, object]]]) -> str:
        """解析整项目默认入口路由。"""

        for route_item in runtime_route_config.get("routes", []):
            route_segment = str(route_item.get("route") or "").strip()
            meta = route_item.get("meta") if isinstance(route_item.get("meta"), dict) else {}
            if route_segment and not bool(meta.get("hidden")):
                return route_segment if route_segment.startswith("/") else f"/{route_segment}"
            for child in route_item.get("children", []) or []:
                child_segment = str(child.get("route") or "").strip()
                child_meta = child.get("meta") if isinstance(child.get("meta"), dict) else {}
                if not child_segment or bool(child_meta.get("hidden")):
                    continue
                parent = route_segment.strip("/")
                child_path = f"/{parent}/{child_segment}" if parent else f"/{child_segment}"
                return re.sub(r"/{2,}", "/", child_path)
        return "/"
