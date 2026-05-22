"""文件功能：封装工作空间的列表、创建、更新和删除业务规则。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_WORKSPACE, create_with_generated_code
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.workspace import Workspace
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.workspace import WorkspaceCreateRequest, WorkspaceItem, WorkspaceUpdateRequest
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.workspace_style_service import WorkspaceStyleService


class WorkspaceService:
    """工作空间服务，负责业务校验和仓储协调。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = WorkspaceRepository(session)
        self.workspace_theme_service = WorkspaceThemeService(session)
        self.workspace_style_service = WorkspaceStyleService(session)

    async def list(self, query: ListQuery, *, user_id: int) -> PagedResponse[WorkspaceItem]:
        """查询当前用户可访问的工作空间列表并转换为标准分页响应。"""

        items, total = await self.repository.list(query, user_id=user_id)
        return PagedResponse[WorkspaceItem](
            items=[await self._to_item(item) for item in items],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, workspace_id: int, *, user_id: int) -> WorkspaceItem:
        """获取当前用户可访问的指定工作空间信息。"""

        workspace = await self.ensure_access(workspace_id, user_id=user_id)
        return await self._to_item(workspace)

    async def create(self, payload: WorkspaceCreateRequest, operator_id: int) -> WorkspaceItem:
        """创建工作空间，code 由系统自动生成。"""

        async def write_workspace(code: str) -> Workspace:
            """使用指定编码创建工作空间并初始化默认主题。"""

            workspace = Workspace(
                code=code,
                name=payload.name,
                description=payload.description,
                status=payload.status.value,
                created_by=operator_id,
                updated_by=operator_id,
            )
            await self.repository.create(workspace)
            await self.repository.create_owner_member(
                workspace_id=workspace.id,
                user_id=operator_id,
                operator_id=operator_id,
            )
            await self.workspace_theme_service.create_default_theme_for_workspace(workspace, operator_id)
            await self.workspace_style_service.create_default_style_for_workspace(workspace, operator_id)
            return workspace

        workspace = await create_with_generated_code(
            self.session,
            Workspace,
            CODE_PREFIX_WORKSPACE,
            write_workspace,
        )
        await self.session.refresh(workspace)
        return await self._to_item(workspace)

    async def update(self, workspace_id: int, payload: WorkspaceUpdateRequest, operator_id: int) -> WorkspaceItem:
        """更新工作空间元数据，编码不可修改。"""

        workspace = await self.ensure_access(workspace_id, user_id=operator_id)

        if payload.name is not None:
            workspace.name = payload.name
        if payload.description is not None:
            workspace.description = payload.description
        if payload.status is not None:
            workspace.status = payload.status.value
        if payload.default_theme_key is not None:
            workspace.default_theme_key = await self.workspace_theme_service.ensure_theme_key_exists(
                workspace_id,
                payload.default_theme_key,
            )

        workspace.updated_by = operator_id
        await self.session.commit()
        await self.session.refresh(workspace)
        return await self._to_item(workspace)

    async def touch(self, workspace_id: int, *, user_id: int) -> WorkspaceItem:
        """更新当前用户可访问工作空间的最后访问时间。"""

        workspace = await self.ensure_access(workspace_id, user_id=user_id)

        workspace.last_opened_at = utc_now()
        await self.session.commit()
        await self.session.refresh(workspace)
        return await self._to_item(workspace)

    async def delete(self, workspace_id: int, *, user_id: int) -> None:
        """删除当前用户可访问的工作空间前先校验是否仍有有效项目。"""

        workspace = await self.ensure_access(workspace_id, user_id=user_id)
        if await self.repository.has_active_projects(workspace_id):
            raise AppException(status_code=409, code="WORKSPACE_HAS_PROJECTS", detail="当前工作空间下仍有项目，无法删除。")

        workspace.deleted_at = utc_now()
        await self.session.commit()

    async def ensure_access(self, workspace_id: int, *, user_id: int) -> Workspace:
        """校验用户是工作空间成员，并返回未删除工作空间。"""

        workspace = await self.repository.get_by_id(workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")
        if not await self.repository.has_active_member(workspace_id=workspace_id, user_id=user_id):
            raise AppException(status_code=403, code="WORKSPACE_ACCESS_DENIED", detail="无权访问该工作空间。")
        return workspace

    async def _to_item(self, workspace: Workspace) -> WorkspaceItem:
        """将工作空间对象转换为响应模型。"""

        return WorkspaceItem.model_validate(
            {
                "id": workspace.id,
                "code": workspace.code,
                "name": workspace.name,
                "description": workspace.description,
                "status": workspace.status,
                "last_opened_at": workspace.last_opened_at,
                "default_theme_key": workspace.default_theme_key,
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at,
                "created_by": workspace.created_by,
                "updated_by": workspace.updated_by,
            }
        )
