"""文件功能：为工作空间组件生成无状态预览 artifact，并复用 Runtime 远程模块链路。"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_PROJECT, create_with_generated_code
from app.core.component_preview_schema import parse_component_preview_schema_text
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.runtime_module_policy import build_runtime_module_resolver_config
from app.models.enums import PageFileType, RecordStatus
from app.models.workspace import Project, Workspace
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.module_dependency_repository import (
    DEPENDENCY_KIND_COMPONENT,
    ModuleDependencyRepository,
)
from app.repositories.project_repository import ProjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.schemas.component_preview_options import ComponentPreviewOptions
from app.schemas.project_app_config import (
    DEFAULT_PAGE_HEIGHT,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PROJECT_BASE_FONT_SIZE,
    DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
    DEFAULT_PROJECT_MENU_MODE,
    DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
    build_project_app_config_document,
)
from app.schemas.release import PreviewArtifactResponse, PreviewEntryDescriptor
from app.services.component_dependency_service import ComponentDependencyService
from app.services.component_preview_options_service import ComponentPreviewOptionsService
from app.services.preview_service import PreviewService
from app.services.project_config_service import ProjectConfigService
from app.services.runtime_icon_service import RuntimeIconService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService
from app.services.workspace_font_service import WorkspaceFontService
from app.services.workspace_theme_service import WorkspaceThemeService

SYSTEM_PREVIEW_PROJECT_NAME = "组件预览沙箱"
SYSTEM_PREVIEW_PROJECT_DESCRIPTION = "系统自动维护的工作空间组件预览沙箱项目，请勿手动编辑。"
TEMP_COMPONENT_VERSION_NO = 0


class ComponentPreviewService:
    """组件预览服务，负责创建工作空间级预览 artifact。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_repository = ProjectRepository(session)
        self.workspace_repository = WorkspaceRepository(session)
        self.project_config_service = ProjectConfigService(session)
        self.component_preview_options_service = ComponentPreviewOptionsService(session)
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)
        self.module_dependency_repository = ModuleDependencyRepository(session)
        self.component_dependency_service = ComponentDependencyService(session)
        self.preview_service = PreviewService(session)
        self.workspace_theme_service = WorkspaceThemeService(session)
        self.runtime_icon_service = RuntimeIconService(session)

    async def create_preview_artifact(self, component_id: int, tenant_id: str) -> PreviewArtifactResponse:
        """为组件最新已发布版本创建无状态预览 artifact。"""

        component = await self._get_component_or_raise(component_id)
        component_version = await self._get_current_component_version_or_raise(component)
        return await self._create_saved_version_preview_artifact(
            component=component,
            component_version=component_version,
            tenant_id=tenant_id,
        )

    async def create_version_preview_artifact(
        self,
        component_id: int,
        version_no: int,
        tenant_id: str,
    ) -> PreviewArtifactResponse:
        """为组件指定已发布版本创建无状态预览 artifact。"""

        component = await self._get_component_or_raise(component_id)
        component_version = await self.component_version_repository.get_by_component_and_version(component.id, version_no)
        if component_version is None:
            raise AppException(status_code=404, code="COMPONENT_VERSION_NOT_FOUND", detail="组件版本不存在。")
        return await self._create_saved_version_preview_artifact(
            component=component,
            component_version=component_version,
            tenant_id=tenant_id,
        )

    async def _create_saved_version_preview_artifact(
        self,
        *,
        component: WorkspaceComponent,
        component_version: WorkspaceComponentVersion,
        tenant_id: str,
    ) -> PreviewArtifactResponse:
        """基于给定发布版本构建组件预览 artifact。"""

        settings = get_settings()
        workspace = await self._get_workspace_or_raise(component.workspace_id)
        sandbox_project = await self._ensure_workspace_preview_project(component.workspace_id)
        resolved_preview_options = await self.component_preview_options_service.resolve_options(workspace)

        component_import_path = self._build_component_import_path(component.code, component_version.version_no)
        modules_metadata, modules_data = await self._build_release_module_graph(component_version.id)
        config_bundle = await self._build_preview_config_bundle(
            workspace=workspace,
            preview_options=resolved_preview_options,
            component_display_name=component.name,
            component_version_no=component_version.version_no,
            component_import_path=component_import_path,
            component_code=component.code,
            preview_schema=component_version.preview_schema,
            modules_data=modules_data,
        )
        await self._commit_metadata_backfills()
        asset_mapping, asset_metadata = await self.preview_service._build_workspace_asset_mapping(component.workspace_id)
        asset_base_url = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{component.workspace_id}"
        entry_descriptor = self._build_entry_descriptor()
        entry_descriptor_payload = entry_descriptor.model_dump(mode="python", exclude_none=True)

        manifest = {
            "artifact_kind": "preview_artifact",
            "tenant_id": tenant_id,
            "preview_kind": "component",
            "owner_scope": {
                "scope_type": "workspace_component",
                "workspace_id": str(component.workspace_id),
                "component_code": component.code,
                "component_version_no": component_version.version_no,
                "preview_mode": "saved",
            },
            "entry_descriptor": entry_descriptor_payload,
            "asset_base_url": asset_base_url,
            "component_preview_mode": "saved",
            "component_code": component.code,
            "component_version_no": component_version.version_no,
            "modules": modules_metadata,
            "assets": asset_mapping,
            "asset_metadata": asset_metadata,
        }
        artifact_id = await RuntimeArtifactStore().put_artifact(
            tenant_id=tenant_id,
            workspace_id=component.workspace_id,
            project_id=sandbox_project.id,
            artifact_kind="preview_artifact",
            manifest=manifest,
            config_bundle=config_bundle,
            modules_data=modules_data,
        )
        preview_token = TokenService.generate_preview_context_token(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            preview_kind="component",
            scope_type="workspace_component",
            workspace_id=component.workspace_id,
            entry_descriptor=entry_descriptor_payload,
            asset_base_url=asset_base_url,
            trace_id=f"req-{uuid.uuid4().hex[:8]}",
            component_preview_mode="saved",
            component_source="workspace_component",
            component_code=component.code,
            component_version_no=component_version.version_no,
        )
        preview_url = (
            f"{settings.backend_public_base_url.rstrip('/')}/preview/artifacts/"
            f"{artifact_id}?{urlencode({'token': preview_token})}"
        )

        return PreviewArtifactResponse(
            preview_url=preview_url,
            artifact_id=artifact_id,
            preview_kind="component",
            entry_descriptor=entry_descriptor,
            viewport_width=resolved_preview_options.page.width,
            viewport_height=resolved_preview_options.page.height,
            workspace_id=component.workspace_id,
            component_preview_mode="saved",
            component_source="workspace_component",
            component_code=component.code,
            component_version_no=component_version.version_no,
        )

    async def create_source_preview_artifact(
        self,
        *,
        workspace_id: int,
        content: str,
        preview_schema: str | None,
        preview_options: ComponentPreviewOptions | dict[str, object] | None,
        tenant_id: str,
        component_id: int | None = None,
        component_name: str | None = None,
        file_type: PageFileType | str = PageFileType.VUE,
    ) -> PreviewArtifactResponse:
        """基于未保存源码创建组件草稿预览 artifact，不写入组件历史。"""

        normalized_file_type = file_type.value if isinstance(file_type, PageFileType) else str(file_type)
        if normalized_file_type != PageFileType.VUE.value:
            raise AppException(status_code=400, code="COMPONENT_FILE_TYPE_INVALID", detail="当前阶段仅支持 Vue 组件。")

        settings = get_settings()
        workspace = await self._get_workspace_or_raise(workspace_id)
        component = None
        component_version = None
        if component_id is not None:
            component = await self._get_component_or_raise(component_id)
            if component.workspace_id != workspace_id:
                raise AppException(status_code=400, code="COMPONENT_WORKSPACE_MISMATCH", detail="组件与工作空间不匹配。")
            component_version = await self._get_current_component_version_or_none(component)

        sandbox_project = await self._ensure_workspace_preview_project(workspace_id)
        resolved_preview_options = await self.component_preview_options_service.resolve_options(
            workspace,
            preview_options,
        )
        draft_component_code = component.code if component is not None else self._build_transient_component_code()
        draft_component_version_no = component_version.version_no if component_version is not None else TEMP_COMPONENT_VERSION_NO
        draft_component_name = component_name or (component.name if component is not None else "未保存组件草稿")
        component_import_path = self._build_component_import_path(draft_component_code, draft_component_version_no)
        modules_metadata, modules_data = await self._build_transient_release_module_graph(
            workspace_id=workspace_id,
            root_component_code=draft_component_code,
            root_component_version_no=draft_component_version_no,
            root_component_content=content,
            root_component_version_id=component_version.id if component_version is not None else None,
        )
        config_bundle = await self._build_preview_config_bundle(
            workspace=workspace,
            preview_options=resolved_preview_options,
            component_display_name=draft_component_name,
            component_version_no=draft_component_version_no,
            component_import_path=component_import_path,
            component_code=draft_component_code,
            preview_schema=preview_schema,
            modules_data=modules_data,
        )
        await self._commit_metadata_backfills()
        asset_mapping, asset_metadata = await self.preview_service._build_workspace_asset_mapping(workspace_id)
        asset_base_url = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}"
        entry_descriptor = self._build_entry_descriptor()
        entry_descriptor_payload = entry_descriptor.model_dump(mode="python", exclude_none=True)

        manifest = {
            "artifact_kind": "preview_artifact",
            "tenant_id": tenant_id,
            "preview_kind": "component",
            "owner_scope": {
                "scope_type": "workspace_component",
                "workspace_id": str(workspace_id),
                "component_code": draft_component_code,
                "component_version_no": draft_component_version_no,
                "preview_mode": "draft",
            },
            "entry_descriptor": entry_descriptor_payload,
            "asset_base_url": asset_base_url,
            "component_preview_mode": "draft",
            "component_code": draft_component_code,
            "component_version_no": draft_component_version_no,
            "modules": modules_metadata,
            "assets": asset_mapping,
            "asset_metadata": asset_metadata,
        }
        artifact_id = await RuntimeArtifactStore().put_artifact(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            project_id=sandbox_project.id,
            artifact_kind="preview_artifact",
            manifest=manifest,
            config_bundle=config_bundle,
            modules_data=modules_data,
        )
        preview_token = TokenService.generate_preview_context_token(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            preview_kind="component",
            scope_type="workspace_component",
            workspace_id=workspace_id,
            entry_descriptor=entry_descriptor_payload,
            asset_base_url=asset_base_url,
            trace_id=f"req-{uuid.uuid4().hex[:8]}",
            component_preview_mode="draft",
            component_source="workspace_component",
            component_code=draft_component_code,
            component_version_no=draft_component_version_no,
        )
        preview_url = (
            f"{settings.backend_public_base_url.rstrip('/')}/preview/artifacts/"
            f"{artifact_id}?{urlencode({'token': preview_token})}"
        )

        return PreviewArtifactResponse(
            preview_url=preview_url,
            artifact_id=artifact_id,
            preview_kind="component",
            entry_descriptor=entry_descriptor,
            viewport_width=resolved_preview_options.page.width,
            viewport_height=resolved_preview_options.page.height,
            workspace_id=workspace_id,
            component_preview_mode="draft",
            component_source="workspace_component",
            component_code=draft_component_code,
            component_version_no=draft_component_version_no,
        )

    async def _get_workspace_or_raise(self, workspace_id: int) -> Workspace:
        """按主键读取工作空间，不存在时抛出标准错误。"""

        workspace = await self.workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
        return workspace

    async def _get_component_or_raise(self, component_id: int) -> WorkspaceComponent:
        """按主键读取组件，不存在时抛出标准错误。"""

        component = await self.component_repository.get_by_id(component_id)
        if component is None:
            raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail="组件不存在。")
        return component

    async def _get_current_component_version_or_none(self, component: WorkspaceComponent) -> WorkspaceComponentVersion | None:
        """读取组件最新发布版本；组件未发布时返回空。"""

        if component.current_version_no <= 0:
            return None

        return await self.component_version_repository.get_by_component_and_version(
            component.id,
            component.current_version_no,
        )

    async def _get_current_component_version_or_raise(self, component: WorkspaceComponent) -> WorkspaceComponentVersion:
        """读取组件最新发布版本，缺失时拒绝生成已发布预览。"""

        version = await self._get_current_component_version_or_none(component)
        if version is None:
            raise AppException(
                status_code=409,
                code="COMPONENT_PUBLISHED_VERSION_MISSING",
                detail="组件尚未发布正式版本，无法生成已发布版本预览。",
            )
        return version

    async def _ensure_workspace_preview_project(self, workspace_id: int) -> Project:
        """确保每个工作空间存在一个系统维护的组件预览沙箱项目。"""

        existing_project = await self.project_repository.get_system_managed_by_workspace(workspace_id)
        if existing_project is not None:
            return existing_project

        if not await self.project_repository.workspace_exists(workspace_id):
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
        workspace = await self._get_workspace_or_raise(workspace_id)

        default_templates = self.project_config_service.get_default_templates()
        config_values = self.project_config_service.build_create_config_values(
            theme_config_yaml=default_templates["themes"],
        )
        default_theme_key = workspace.default_theme_key

        async def write_preview_project(code: str) -> Project:
            """使用指定编码创建系统维护的组件预览项目。"""

            preview_project = Project(
                workspace_id=workspace_id,
                code=code,
                name=SYSTEM_PREVIEW_PROJECT_NAME,
                description=SYSTEM_PREVIEW_PROJECT_DESCRIPTION,
                is_system_managed=True,
                status=RecordStatus.ACTIVE.value,
                page_width=DEFAULT_PAGE_WIDTH,
                page_height=DEFAULT_PAGE_HEIGHT,
                base_font_size=DEFAULT_PROJECT_BASE_FONT_SIZE,
                icon_default_stroke_width=DEFAULT_PROJECT_ICON_DEFAULT_STROKE_WIDTH,
                show_pdf_export_button=DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
                menu_mode=DEFAULT_PROJECT_MENU_MODE,
                theme_key=default_theme_key,
                theme_config_yaml=config_values["theme_config_yaml"],
            )
            await self.project_repository.create(preview_project)
            return preview_project

        preview_project = await create_with_generated_code(
            self.session,
            Project,
            CODE_PREFIX_PROJECT,
            write_preview_project,
        )
        reloaded_project = await self.project_repository.get_by_id(preview_project.id)
        if reloaded_project is None:
            raise AppException(status_code=500, code="PREVIEW_PROJECT_CREATE_FAILED", detail="组件预览沙箱项目创建失败。")
        return reloaded_project

    async def _build_preview_config_bundle(
        self,
        *,
        workspace: Workspace,
        preview_options: ComponentPreviewOptions,
        component_display_name: str,
        component_version_no: int | None,
        component_import_path: str,
        component_code: str,
        preview_schema: str | None,
        modules_data: list[dict[str, str]],
        component_source: str = "workspace_component",
        runtime_kit_component_name: str | None = None,
        runtime_kit_manifest_version: str | None = None,
    ) -> dict[str, object]:
        """构建组件纯沙箱预览所需的预加载配置包。"""

        resolved_theme_config: dict[str, object]
        resolved_project_icon_name: str | None
        font_service = WorkspaceFontService(self.session)
        declared_font_asset_names = font_service.collect_declared_font_asset_names_from_modules(modules_data)
        if str(preview_options.page.theme_key or "").strip():
            resolved_theme_config = await self.workspace_theme_service.build_theme_config_document_by_key(
                workspace.id,
                preview_options.page.theme_key,
            )
            resolved_project_icon_name = await self.workspace_theme_service.get_project_icon_name_by_key(
                workspace.id,
                preview_options.page.theme_key,
            )
            font_bundle = await font_service.build_font_bundle_for_theme_key(
                workspace.id,
                preview_options.page.theme_key,
                explicit_asset_names=declared_font_asset_names,
            )
        else:
            resolved_theme_config = self._parse_yaml_object_config(
                yaml_text=preview_options.page.theme_config_yaml or "",
                empty_fallback="themes: {}",
                field_name="theme.config.yaml",
            )
            resolved_project_icon_name = self.project_config_service.resolve_project_icon_name_from_theme_config(
                resolved_theme_config
            )
            font_bundle = await font_service.build_font_bundle_for_workspace(
                workspace.id,
                explicit_asset_names=declared_font_asset_names,
            )
        parsed_app_config = build_project_app_config_document(
            title="",
            description=None,
            icon=resolved_project_icon_name,
            page_width=preview_options.page.width,
            page_height=preview_options.page.height,
            base_font_size=preview_options.page.base_font_size,
            icon_default_stroke_width=preview_options.page.icon_default_stroke_width,
            show_pdf_export_button=DEFAULT_PROJECT_SHOW_PDF_EXPORT_BUTTON,
            menu_mode=DEFAULT_PROJECT_MENU_MODE,
        )
        icon_config = await self.runtime_icon_service.build_component_icon_config_from_modules(
            workspace_id=workspace.id,
            modules_data=modules_data,
            extra_icon_names=[resolved_project_icon_name] if resolved_project_icon_name else None,
        )

        component_preview_payload: dict[str, object] = {
            "component_import_path": component_import_path,
            "component_source": component_source,
            "component_code": component_code,
            "display_name": component_display_name,
            "schema": parse_component_preview_schema_text(preview_schema),
            "placement": preview_options.placement.model_dump(mode="python"),
        }
        if component_version_no is not None:
            component_preview_payload["component_version_no"] = component_version_no
        if runtime_kit_component_name:
            component_preview_payload["runtime_kit_component_name"] = runtime_kit_component_name
        if runtime_kit_manifest_version:
            component_preview_payload["runtime_kit_manifest_version"] = runtime_kit_manifest_version

        config_bundle = {
            "app": parsed_app_config.model_dump(mode="python"),
            "routes": {"routes": []},
            "icons": icon_config,
            "themes": resolved_theme_config,
            "fonts": font_bundle.model_dump(),
            "module_resolver": build_runtime_module_resolver_config(),
            "component_preview": component_preview_payload,
        }
        return config_bundle

    async def _commit_metadata_backfills(self) -> None:
        """提交构建配置包时顺带补齐的资源分析元数据。"""

        if self.session.dirty:
            await self.session.commit()

    @staticmethod
    def _build_entry_descriptor() -> PreviewEntryDescriptor:
        """返回组件预览固定使用的宿主页入口描述。"""

        return PreviewEntryDescriptor(entry_type="component_host")

    @staticmethod
    def _parse_yaml_object_config(*, yaml_text: str, empty_fallback: str, field_name: str) -> dict[str, Any]:
        """解析并校验 YAML 对象配置，确保 config_bundle 下发结构稳定。"""

        try:
            parsed_value = yaml.safe_load(yaml_text or empty_fallback) or {}
        except yaml.YAMLError as exc:
            raise AppException(
                status_code=400,
                code="PROJECT_CONFIG_INVALID_YAML",
                detail=f"{field_name} YAML 语法错误：{exc}",
            ) from exc

        if not isinstance(parsed_value, dict):
            raise AppException(
                status_code=400,
                code="PROJECT_CONFIG_INVALID_YAML",
                detail=f"{field_name} 必须是 YAML 对象。",
            )
        return parsed_value

    async def _build_release_module_graph(self, root_component_version_id: int) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
        """递归收集目标组件和其依赖组件的完整模块图。"""

        modules_metadata: dict[str, dict[str, str]] = {}
        modules_data_by_path: dict[str, dict[str, str]] = {}
        queued_component_version_ids: list[int] = [root_component_version_id]
        visited_component_version_ids: set[int] = set()

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

            logical_path = PreviewService._build_component_logical_path(component.code, component_version.version_no)
            PreviewService._append_release_module(
                modules_metadata=modules_metadata,
                modules_data_by_path=modules_data_by_path,
                logical_path=logical_path,
                content=component_version.content,
                include_in_manifest=True,
            )

            dependency_items = await self.module_dependency_repository.list_component_version_dependencies(component_version.id)
            for dependency_item in dependency_items:
                if (
                    dependency_item.dependency_kind == DEPENDENCY_KIND_COMPONENT
                    and dependency_item.dependency_component_version_id is not None
                ):
                    queued_component_version_ids.append(dependency_item.dependency_component_version_id)

        return modules_metadata, list(modules_data_by_path.values())

    async def _build_transient_release_module_graph(
        self,
        *,
        workspace_id: int,
        root_component_code: str,
        root_component_version_no: int,
        root_component_content: str,
        root_component_version_id: int | None,
    ) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
        """基于未保存源码收集临时根组件及其传递依赖模块图。"""

        parsed_dependencies = self.component_dependency_service.parse_dependencies(
            root_component_content,
            source_label=f"组件 {root_component_code}",
        )
        resolved_component_dependencies = await self.component_dependency_service.resolve_component_dependencies(
            workspace_id=workspace_id,
            component_refs=parsed_dependencies.component_imports,
            source_label=f"组件 {root_component_code}",
        )
        await self.component_dependency_service.assert_transient_component_dependencies_have_no_cycle(
            root_component_version_id=root_component_version_id,
            dependency_version_ids=[item.component_version_id for item in resolved_component_dependencies],
        )

        modules_metadata: dict[str, dict[str, str]] = {}
        modules_data_by_path: dict[str, dict[str, str]] = {}
        logical_path = PreviewService._build_component_logical_path(root_component_code, root_component_version_no)
        PreviewService._append_release_module(
            modules_metadata=modules_metadata,
            modules_data_by_path=modules_data_by_path,
            logical_path=logical_path,
            content=root_component_content,
            include_in_manifest=True,
        )

        queued_component_version_ids = [item.component_version_id for item in resolved_component_dependencies]
        visited_component_version_ids: set[int] = set()
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

            dependency_logical_path = PreviewService._build_component_logical_path(component.code, component_version.version_no)
            PreviewService._append_release_module(
                modules_metadata=modules_metadata,
                modules_data_by_path=modules_data_by_path,
                logical_path=dependency_logical_path,
                content=component_version.content,
                include_in_manifest=True,
            )

            dependency_items = await self.module_dependency_repository.list_component_version_dependencies(component_version.id)
            for dependency_item in dependency_items:
                if (
                    dependency_item.dependency_kind == DEPENDENCY_KIND_COMPONENT
                    and dependency_item.dependency_component_version_id is not None
                ):
                    queued_component_version_ids.append(dependency_item.dependency_component_version_id)

        return modules_metadata, list(modules_data_by_path.values())

    @staticmethod
    def _build_component_import_path(component_code: str, version_no: int) -> str:
        """将组件编码和版本号转换为 Runtime 可识别的远程组件别名。"""

        return f"@workspace-components/{component_code}/v/{version_no}"

    @staticmethod
    def _build_transient_component_code() -> str:
        """为未保存组件草稿生成仅预览链路内使用的临时代码。"""

        return f"CMP_DRAFT_{uuid.uuid4().hex[:8].upper()}"
