"""文件功能：封装项目的 CRUD 业务逻辑和工作空间校验规则。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_PROJECT, create_with_generated_code
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.enums import RecordStatus
from app.models.workspace import Project
from app.repositories.project_repository import ProjectRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.project import ProjectCreateRequest, ProjectItem, ProjectUpdateRequest
from app.services.project_config_service import ProjectConfigService
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.workspace_service import WorkspaceService


class ProjectService:
    """项目服务，负责工作空间校验、编码自动生成与软删除处理。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ProjectRepository(session)
        self.workspace_repository = WorkspaceRepository(session)
        self.project_config_service = ProjectConfigService(session)
        self.workspace_theme_service = WorkspaceThemeService(session)
        self.workspace_service = WorkspaceService(session)

    @staticmethod
    def _to_item(project: Project) -> ProjectItem:
        """将 ORM 项目对象转换为接口层需要的显式响应结构。"""

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
                "theme_config_yaml": project.theme_config_yaml,
                "style_spec_markdown": project.style_spec_markdown,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
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
        return PagedResponse[ProjectItem](
            items=[self._to_item(item) for item in items],
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
        return self._to_item(project)

    async def create(self, payload: ProjectCreateRequest, operator_id: int) -> ProjectItem:
        """创建项目，code 由系统自动生成，并校验工作空间存在性。"""

        if not await self.repository.workspace_exists(payload.workspace_id):
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
        await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
        workspace = await self.workspace_repository.get_by_id(payload.workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")

        config_values = self.project_config_service.build_create_config_values(theme_config_yaml=payload.theme_config_yaml)
        resolved_theme_key = payload.theme_key
        if resolved_theme_key is None and payload.theme_config_yaml is None:
            resolved_theme_key = workspace.default_theme_key
        if resolved_theme_key is not None:
            resolved_theme_key = await self.workspace_theme_service.ensure_theme_key_exists(
                payload.workspace_id,
                resolved_theme_key,
            )

        async def write_project(code: str) -> Project:
            """使用指定编码创建项目。"""

            project = Project(
                workspace_id=payload.workspace_id,
                code=code,
                name=payload.name,
                description=payload.description,
                status=payload.status.value,
                archived_at=utc_now() if payload.status == RecordStatus.ARCHIVED else None,
                page_width=payload.page_width,
                page_height=payload.page_height,
                base_font_size=payload.base_font_size,
                icon_default_stroke_width=payload.icon_default_stroke_width,
                show_pdf_export_button=payload.show_pdf_export_button,
                menu_mode=payload.menu_mode,
                theme_key=resolved_theme_key,
                theme_config_yaml=config_values["theme_config_yaml"],
                style_spec_markdown=payload.style_spec_markdown,
                created_by=operator_id,
                updated_by=operator_id,
            )
            await self.repository.create(project)
            return project

        project = await create_with_generated_code(
            self.session,
            Project,
            CODE_PREFIX_PROJECT,
            write_project,
        )
        reloaded = await self.repository.get_by_id(project.id)
        return self._to_item(reloaded)

    async def update(self, project_id: int, payload: ProjectUpdateRequest, operator_id: int) -> ProjectItem:
        """更新项目元数据，编码不可修改。"""

        project = await self.repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        await self.workspace_service.ensure_access(project.workspace_id, user_id=operator_id)

        if payload.workspace_id is not None and payload.workspace_id != project.workspace_id:
            if not await self.repository.workspace_exists(payload.workspace_id):
                raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
            await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
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
        if payload.description is not None:
            project.description = payload.description
        if payload.status is not None:
            previous_status = project.status
            project.status = payload.status.value
            if payload.status == RecordStatus.ARCHIVED:
                project.archived_at = project.archived_at if previous_status == RecordStatus.ARCHIVED.value else utc_now()
            else:
                project.archived_at = None
        if payload.page_width is not None:
            project.page_width = payload.page_width
        if payload.page_height is not None:
            project.page_height = payload.page_height
        if payload.base_font_size is not None:
            project.base_font_size = payload.base_font_size
        if payload.icon_default_stroke_width is not None:
            project.icon_default_stroke_width = payload.icon_default_stroke_width
        if payload.show_pdf_export_button is not None:
            project.show_pdf_export_button = payload.show_pdf_export_button
        if payload.menu_mode is not None:
            project.menu_mode = payload.menu_mode
        if payload.theme_key is not None:
            project.theme_key = await self.workspace_theme_service.ensure_theme_key_exists(
                project.workspace_id,
                payload.theme_key,
            )
        if payload.theme_config_yaml is not None:
            self.project_config_service.validate_yaml_text("themes", payload.theme_config_yaml)
            project.theme_config_yaml = payload.theme_config_yaml
        if payload.style_spec_markdown is not None:
            project.style_spec_markdown = payload.style_spec_markdown

        project.updated_by = operator_id
        await self.session.commit()
        reloaded = await self.repository.get_by_id(project.id)
        return self._to_item(reloaded)

    async def delete(self, project_id: int, *, user_id: int) -> None:
        """对当前用户可访问项目执行软删除，不影响页面资源。"""

        project = await self.repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        await self.workspace_service.ensure_access(project.workspace_id, user_id=user_id)

        project.deleted_at = utc_now()
        await self.session.commit()
