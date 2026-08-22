"""文件功能：封装项目的 CRUD 业务逻辑和工作空间校验规则。"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_PROJECT, create_with_generated_code
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.time_utils import normalize_utc, utc_now
from app.models.enums import RecordStatus
from app.models.page import Page
from app.models.workspace import Project
from app.repositories.project_repository import ProjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.repositories.workspace_style_repository import WorkspaceStyleRepository
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectItem,
    ProjectUpdateRequest,
    normalize_project_build_extra_assets_config,
)
from app.services.project_config_service import ProjectConfigService
from app.services.page_screenshot_url import build_page_screenshot_url
from app.services.project_suggested_reference_asset_service import ProjectSuggestedReferenceAssetService
from app.services.suggested_component_service import SuggestedComponentService
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.workspace_service import WorkspaceService
from app.services.workspace_style_service import DEFAULT_WORKSPACE_STYLE_KEY


class ProjectService:
    """项目服务，负责工作空间校验、编码自动生成与软删除处理。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProjectRepository(session)
        self.workspace_repository = WorkspaceRepository(session)
        self.workspace_style_repository = WorkspaceStyleRepository(session)
        self.project_config_service = ProjectConfigService(session)
        self.workspace_theme_service = WorkspaceThemeService(session)
        self.workspace_service = WorkspaceService(session)
        self.settings = get_settings()

    def _to_item(
        self,
        project: Project,
        *,
        first_page: Page | None = None,
        page_counts: tuple[int, int] = (0, 0),
        latest_page_updated_at: datetime | None = None,
    ) -> ProjectItem:
        """将 ORM 项目对象转换为接口层需要的显式响应结构。"""

        resolved_updated_at = project.updated_at
        if latest_page_updated_at is not None and normalize_utc(latest_page_updated_at) > normalize_utc(resolved_updated_at):
            resolved_updated_at = latest_page_updated_at

        return ProjectItem.model_validate(
            {
                "id": project.id,
                "workspace_id": project.workspace_id,
                "workspace_name": project.workspace.name,
                "code": project.code,
                "name": project.name,
                "description": project.description,
                "is_system_managed": project.is_system_managed,
                "status": project.status,
                "archived_at": project.archived_at,
                "page_width": project.page_width,
                "page_height": project.page_height,
                "base_font_size": project.base_font_size,
                "icon_default_stroke_width": project.icon_default_stroke_width,
                "show_pdf_export_button": project.show_pdf_export_button,
                "menu_mode": project.menu_mode,
                "theme_key": project.theme_key,
                "style_spec_markdown": project.style_spec_markdown,
                "build_extra_assets_json": normalize_project_build_extra_assets_config(
                    project.build_extra_assets_json
                ).model_dump(mode="python"),
                "routed_page_count": page_counts[0],
                "total_page_count": page_counts[1],
                "first_page_title": first_page.title if first_page is not None else None,
                "first_page_screenshot_url": (
                    build_page_screenshot_url(first_page, self.settings.backend_public_base_url)
                    if first_page is not None
                    else None
                ),
                "created_at": project.created_at,
                "updated_at": resolved_updated_at,
                "created_by": project.created_by,
                "updated_by": project.updated_by,
            }
        )

    async def list(self, query: ListQuery, workspace_id: int | None, *, user_id: int) -> PagedResponse[ProjectItem]:
        """按当前用户可访问工作空间筛选项目列表。"""

        if workspace_id is not None:
            await self.workspace_service.ensure_access(workspace_id, user_id=user_id)
        items, total = await self.repository.list(
            query,
            workspace_id,
            include_system_managed=False,
            user_id=user_id,
        )
        first_pages = await self.repository.list_cover_pages([item.id for item in items])
        page_counts = await self.repository.list_page_counts([item.id for item in items])
        latest_page_updated_at = await self.repository.list_page_latest_updated_at([item.id for item in items])
        return PagedResponse[ProjectItem](
            items=[
                self._to_item(
                    item,
                    first_page=first_pages.get(item.id),
                    page_counts=page_counts.get(item.id, (0, 0)),
                    latest_page_updated_at=latest_page_updated_at.get(item.id),
                )
                for item in items
            ],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, project_id: int, *, user_id: int | None = None) -> ProjectItem:
        """获取指定项目详情，并在传入用户时校验工作空间访问权。"""

        project = await self.repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        if user_id is not None:
            await self.workspace_service.ensure_access(project.workspace_id, user_id=user_id)
        page_counts = await self.repository.list_page_counts([project.id])
        latest_page_updated_at = await self.repository.list_page_latest_updated_at([project.id])
        return self._to_item(
            project,
            page_counts=page_counts.get(project.id, (0, 0)),
            latest_page_updated_at=latest_page_updated_at.get(project.id),
        )

    async def create(
        self,
        payload: ProjectCreateRequest,
        operator_id: int,
        *,
        commit: bool = True,
    ) -> ProjectItem:
        """创建项目，code 由系统自动生成，并校验工作空间存在性。"""

        if not await self.repository.workspace_exists(payload.workspace_id):
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
        await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
        workspace = await self.workspace_repository.get_by_id(payload.workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")

        config_values = self.project_config_service.build_create_config_values(theme_config_yaml=None)
        configuration = payload.configuration
        source_style = None
        if configuration.mode in {"default", "style"}:
            source_style = (
                await self.workspace_style_repository.get_by_key(payload.workspace_id, DEFAULT_WORKSPACE_STYLE_KEY)
                if configuration.mode == "default"
                else await self.workspace_style_repository.get_by_id(payload.workspace_id, configuration.style_id)
            )
            if source_style is None:
                raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail="项目初始化样式不存在或不可用。")
            presentation = source_style
        else:
            presentation = configuration.presentation
        resolved_theme_key = presentation.theme_key or workspace.default_theme_key
        resolved_theme_key = await self.workspace_theme_service.ensure_theme_key_exists(payload.workspace_id, resolved_theme_key)

        async def write_project(code: str) -> Project:
            """使用指定编码创建项目。"""

            project = Project(
                workspace_id=payload.workspace_id,
                code=code,
                name=payload.name,
                description=payload.description,
                status=payload.status.value,
                archived_at=utc_now() if payload.status == RecordStatus.ARCHIVED else None,
                page_width=presentation.page_width,
                page_height=presentation.page_height,
                base_font_size=presentation.base_font_size,
                icon_default_stroke_width=presentation.icon_default_stroke_width,
                show_pdf_export_button=presentation.show_pdf_export_button,
                menu_mode=presentation.menu_mode,
                theme_key=resolved_theme_key,
                theme_config_yaml=config_values["theme_config_yaml"],
                style_spec_markdown=presentation.style_spec_markdown,
                build_extra_assets_json=payload.build_extra_assets_json.model_dump(mode="python"),
                created_by=operator_id,
                updated_by=operator_id,
            )
            await self.repository.create(project)
            if source_style is not None:
                await SuggestedComponentService(self.session).copy_style_components_to_project(
                    project.id,
                    source_style.id,
                    workspace_id=payload.workspace_id,
                    commit=False,
                )
            else:
                await SuggestedComponentService(self.session).replace_project_components(
                    project.id,
                    configuration.suggested_components.component_ids,
                    commit=False,
                )
            return project

        project = await create_with_generated_code(
            self.session,
            Project,
            CODE_PREFIX_PROJECT,
            write_project,
            commit=commit,
        )
        if not commit:
            await self.session.flush()
        reloaded = await self.repository.get_by_id(project.id)
        return self._to_item(reloaded)

    async def update(
        self,
        project_id: int,
        payload: ProjectUpdateRequest,
        operator_id: int,
        *,
        commit: bool = True,
    ) -> ProjectItem:
        """更新项目元数据，编码不可修改。"""

        project = await self.repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        await self.workspace_service.ensure_access(project.workspace_id, user_id=operator_id)

        if payload.workspace_id is not None and payload.workspace_id != project.workspace_id:
            if not await self.repository.workspace_exists(payload.workspace_id):
                raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
            await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
            await ProjectSuggestedReferenceAssetService(self.session).clear_project_assets(project_id, commit=False)
            await SuggestedComponentService(self.session).clear_project_components(project_id, commit=False)
            project.workspace_id = payload.workspace_id
            if project.theme_key is not None:
                project.theme_key = await self.workspace_theme_service.ensure_theme_key_exists(
                    payload.workspace_id,
                    project.theme_key,
                )
            else:
                next_workspace = await self.workspace_repository.get_by_id(payload.workspace_id)
                project.theme_key = next_workspace.default_theme_key if next_workspace is not None else None

        if payload.name is not None:
            project.name = payload.name
        if "description" in payload.model_fields_set:
            # 显式传入 null 表示清空描述；未传字段时保持原值。
            project.description = payload.description
        if payload.status is not None:
            previous_status = project.status
            project.status = payload.status.value
            if payload.status == RecordStatus.ARCHIVED:
                project.archived_at = project.archived_at if previous_status == RecordStatus.ARCHIVED.value else utc_now()
            else:
                project.archived_at = None
        if payload.configuration is not None:
            if payload.configuration.mode == "style":
                source_style = await self.workspace_style_repository.get_by_id(project.workspace_id, payload.configuration.style_id)
                if source_style is None:
                    raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail="待应用样式不存在或不可用。")
                for field_name in (
                    "page_width", "page_height", "base_font_size", "icon_default_stroke_width",
                    "show_pdf_export_button", "menu_mode", "style_spec_markdown",
                ):
                    setattr(project, field_name, getattr(source_style, field_name))
                current_workspace = await self.workspace_repository.get_by_id(project.workspace_id)
                project.theme_key = await self.workspace_theme_service.ensure_theme_key_exists(
                    project.workspace_id,
                    source_style.theme_key or (current_workspace.default_theme_key if current_workspace is not None else None),
                )
                await SuggestedComponentService(self.session).copy_style_components_to_project(
                    project.id,
                    source_style.id,
                    workspace_id=project.workspace_id,
                    commit=False,
                )
            else:
                presentation = payload.configuration.presentation
                if presentation is not None:
                    fields = presentation.model_fields_set
                    for field_name in (
                        "page_width", "page_height", "base_font_size", "icon_default_stroke_width",
                        "show_pdf_export_button", "menu_mode", "style_spec_markdown",
                    ):
                        if field_name in fields:
                            setattr(project, field_name, getattr(presentation, field_name))
                    if "theme_key" in fields:
                        workspace = await self.workspace_repository.get_by_id(project.workspace_id)
                        project.theme_key = await self.workspace_theme_service.ensure_theme_key_exists(
                            project.workspace_id,
                            presentation.theme_key or (workspace.default_theme_key if workspace is not None else None),
                        )
                if payload.configuration.suggested_components is not None:
                    await SuggestedComponentService(self.session).replace_project_components(
                        project.id,
                        payload.configuration.suggested_components.component_ids,
                        commit=False,
                    )
        if payload.build_extra_assets_json is not None:
            project.build_extra_assets_json = payload.build_extra_assets_json.model_dump(mode="python")
        project.updated_by = operator_id
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        reloaded = await self.repository.get_by_id(project.id)
        page_counts = await self.repository.list_page_counts([project.id])
        return self._to_item(reloaded, page_counts=page_counts.get(project.id, (0, 0)))

    async def delete(self, project_id: int, *, user_id: int, commit: bool = True) -> None:
        """对当前用户可访问项目执行软删除，不影响页面资源。"""

        project = await self.repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        await self.workspace_service.ensure_access(project.workspace_id, user_id=user_id)

        project.deleted_at = utc_now()
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
