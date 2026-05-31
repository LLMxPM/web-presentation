"""文件功能：封装工作空间组件实体的数据访问逻辑。"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.enums import RecordStatus
from app.models.workspace import Workspace, WorkspaceMember
from app.models.workspace_component import WorkspaceComponent
from app.schemas.component import WorkspaceComponentListQuery


class WorkspaceComponentRepository:
    """工作空间组件仓储，负责组件查询、分页与持久化。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, query: WorkspaceComponentListQuery, *, user_id: int | None = None) -> tuple[list[WorkspaceComponent], int]:
        """按统一分页条件返回当前用户可访问组件列表和总数。"""

        workspace_alias = aliased(Workspace)
        statement = (
            select(WorkspaceComponent, workspace_alias.name.label("workspace_name"))
            .where(WorkspaceComponent.deleted_at.is_(None))
            .outerjoin(workspace_alias, WorkspaceComponent.workspace_id == workspace_alias.id)
        )
        count_statement = select(func.count(WorkspaceComponent.id)).where(WorkspaceComponent.deleted_at.is_(None))
        if user_id is not None:
            access_condition = (
                select(WorkspaceMember.id)
                .where(WorkspaceMember.workspace_id == WorkspaceComponent.workspace_id)
                .where(WorkspaceMember.user_id == user_id)
                .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
                .exists()
            )
            statement = statement.where(access_condition)
            count_statement = count_statement.where(access_condition)

        if query.keyword:
            keyword = f"%{query.keyword}%"
            condition = or_(
                WorkspaceComponent.code.ilike(keyword),
                WorkspaceComponent.name.ilike(keyword),
                WorkspaceComponent.import_name.ilike(keyword),
                WorkspaceComponent.summary.ilike(keyword),
                WorkspaceComponent.component_type.ilike(keyword),
            )
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        if query.component_type:
            component_type = query.component_type.value
            statement = statement.where(WorkspaceComponent.component_type == component_type)
            count_statement = count_statement.where(WorkspaceComponent.component_type == component_type)
        if query.status:
            statement = statement.where(WorkspaceComponent.status == query.status.value)
            count_statement = count_statement.where(WorkspaceComponent.status == query.status.value)
        if query.workspace_id is not None:
            statement = statement.where(WorkspaceComponent.workspace_id == query.workspace_id)
            count_statement = count_statement.where(WorkspaceComponent.workspace_id == query.workspace_id)
        if query.published_only:
            statement = statement.where(WorkspaceComponent.current_version_no > 0)
            count_statement = count_statement.where(WorkspaceComponent.current_version_no > 0)

        sort_column = getattr(WorkspaceComponent, query.sort_by, WorkspaceComponent.updated_at)
        sort_expression = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        statement = statement.order_by(sort_expression).offset((query.page - 1) * query.page_size).limit(query.page_size)
        total = int(await self.session.scalar(count_statement) or 0)
        result = await self.session.execute(statement)

        items: list[WorkspaceComponent] = []
        for row in result.all():
            component = row.WorkspaceComponent
            component.workspace_name = row.workspace_name
            items.append(component)
        return items, total

    async def get_by_id(self, component_id: int) -> WorkspaceComponent | None:
        """按主键查询未删除组件。"""

        workspace_alias = aliased(Workspace)
        statement = (
            select(WorkspaceComponent, workspace_alias.name.label("workspace_name"))
            .where(WorkspaceComponent.id == component_id)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .outerjoin(workspace_alias, WorkspaceComponent.workspace_id == workspace_alias.id)
        )
        row = (await self.session.execute(statement)).first()
        if not row:
            return None

        component = row.WorkspaceComponent
        component.workspace_name = row.workspace_name
        return component

    async def get_by_code(self, code: str) -> WorkspaceComponent | None:
        """按业务编码查询未删除组件。"""

        return await self.session.scalar(
            select(WorkspaceComponent)
            .where(WorkspaceComponent.code == code)
            .where(WorkspaceComponent.deleted_at.is_(None))
        )

    async def get_active_by_import_name(
        self,
        *,
        workspace_id: int,
        import_name: str,
        exclude_component_id: int | None = None,
    ) -> WorkspaceComponent | None:
        """按工作空间和源码引用名查询启用组件，用于创建或更新前唯一性校验。"""

        statement = (
            select(WorkspaceComponent)
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.import_name == import_name)
            .where(WorkspaceComponent.status == "active")
            .where(WorkspaceComponent.deleted_at.is_(None))
        )
        if exclude_component_id is not None:
            statement = statement.where(WorkspaceComponent.id != exclude_component_id)
        return await self.session.scalar(statement)

    async def workspace_exists(self, workspace_id: int) -> bool:
        """校验工作空间是否存在且未删除。"""

        total = await self.session.scalar(
            select(func.count(Workspace.id))
            .where(Workspace.id == workspace_id)
            .where(Workspace.deleted_at.is_(None))
        )
        return bool(total)

    async def create(self, component: WorkspaceComponent) -> WorkspaceComponent:
        """持久化新组件。"""

        self.session.add(component)
        await self.session.flush()
        return component
