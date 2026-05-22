"""文件功能：封装工作空间的列表、查询与软删除访问逻辑。"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecordStatus, WorkspaceMemberRole
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.common import ListQuery


class WorkspaceRepository:
    """工作空间仓储，负责基础 CRUD 查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, query: ListQuery, *, user_id: int) -> tuple[list[Workspace], int]:
        """按统一分页条件返回当前用户可访问的工作空间列表与总数。"""

        access_condition = (
            select(WorkspaceMember.id)
            .where(WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
            .exists()
        )
        statement = select(Workspace).where(Workspace.deleted_at.is_(None)).where(access_condition)
        count_statement = select(func.count(Workspace.id)).where(Workspace.deleted_at.is_(None)).where(access_condition)

        if query.keyword:
            keyword = f"%{query.keyword}%"
            condition = or_(Workspace.name.ilike(keyword), Workspace.code.ilike(keyword))
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        if query.status:
            statement = statement.where(Workspace.status == query.status.value)
            count_statement = count_statement.where(Workspace.status == query.status.value)

        sort_column = getattr(Workspace, query.sort_by, Workspace.updated_at)
        sort_expression = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        statement = statement.order_by(sort_expression).offset((query.page - 1) * query.page_size).limit(query.page_size)
        total = int(await self.session.scalar(count_statement) or 0)
        result = await self.session.scalars(statement)
        return list(result), total

    async def get_by_id(self, workspace_id: int) -> Workspace | None:
        """按主键查询未删除的工作空间。"""

        return await self.session.scalar(
            select(Workspace).where(Workspace.id == workspace_id).where(Workspace.deleted_at.is_(None))
        )

    async def get_by_code(self, code: str) -> Workspace | None:
        """按业务编码查询未删除的工作空间。"""

        return await self.session.scalar(
            select(Workspace).where(Workspace.code == code).where(Workspace.deleted_at.is_(None))
        )

    async def create(self, workspace: Workspace) -> Workspace:
        """持久化新工作空间。"""

        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def create_owner_member(self, *, workspace_id: int, user_id: int, operator_id: int) -> WorkspaceMember:
        """为新建工作空间写入创建者 owner 成员关系。"""

        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=user_id,
            role=WorkspaceMemberRole.OWNER.value,
            status=RecordStatus.ACTIVE.value,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def has_active_member(self, *, workspace_id: int, user_id: int) -> bool:
        """判断指定用户是否是工作空间启用成员。"""

        total = await self.session.scalar(
            select(func.count(WorkspaceMember.id))
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user_id)
            .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
        )
        return bool(total)

    async def has_active_projects(self, workspace_id: int) -> bool:
        """判断工作空间下是否仍存在未删除项目。"""

        total = await self.session.scalar(
            select(func.count(Project.id))
            .where(Project.workspace_id == workspace_id)
            .where(Project.deleted_at.is_(None))
        )
        return bool(total)
