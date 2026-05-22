"""文件功能：封装项目实体的数据访问逻辑。"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import RecordStatus
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.common import ListQuery


class ProjectRepository:
    """项目仓储，负责项目列表、查询与持久化。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        query: ListQuery,
        workspace_id: int | None = None,
        *,
        include_system_managed: bool = False,
        user_id: int | None = None,
    ) -> tuple[list[Project], int]:
        """按分页条件和工作空间筛选返回项目列表。"""

        statement = select(Project).options(selectinload(Project.workspace)).where(Project.deleted_at.is_(None))
        count_statement = select(func.count(Project.id)).where(Project.deleted_at.is_(None))
        if not include_system_managed:
            statement = statement.where(Project.is_system_managed.is_(False))
            count_statement = count_statement.where(Project.is_system_managed.is_(False))
        if user_id is not None:
            access_condition = (
                select(WorkspaceMember.id)
                .where(WorkspaceMember.workspace_id == Project.workspace_id)
                .where(WorkspaceMember.user_id == user_id)
                .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
                .exists()
            )
            statement = statement.where(access_condition)
            count_statement = count_statement.where(access_condition)

        if workspace_id is not None:
            statement = statement.where(Project.workspace_id == workspace_id)
            count_statement = count_statement.where(Project.workspace_id == workspace_id)
        if query.keyword:
            keyword = f"%{query.keyword}%"
            condition = or_(Project.name.ilike(keyword), Project.code.ilike(keyword))
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        if query.status:
            statement = statement.where(Project.status == query.status.value)
            count_statement = count_statement.where(Project.status == query.status.value)

        sort_column = getattr(Project, query.sort_by, Project.updated_at)
        sort_expression = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        statement = statement.order_by(sort_expression).offset((query.page - 1) * query.page_size).limit(query.page_size)
        total = int(await self.session.scalar(count_statement) or 0)
        result = await self.session.scalars(statement)
        return list(result), total

    async def get_by_id(self, project_id: int) -> Project | None:
        """按主键查询未删除项目。"""

        return await self.session.scalar(
            select(Project)
            .options(selectinload(Project.workspace))
            .where(Project.id == project_id)
            .where(Project.deleted_at.is_(None))
        )

    async def get_by_code(self, code: str) -> Project | None:
        """按业务编码查询未删除项目。"""

        return await self.session.scalar(
            select(Project).where(Project.code == code).where(Project.deleted_at.is_(None))
        )

    async def get_system_managed_by_workspace(self, workspace_id: int) -> Project | None:
        """读取指定工作空间下的系统管理项目。"""

        return await self.session.scalar(
            select(Project)
            .options(selectinload(Project.workspace))
            .where(Project.workspace_id == workspace_id)
            .where(Project.is_system_managed.is_(True))
            .where(Project.deleted_at.is_(None))
            .order_by(Project.id.asc())
            .limit(1)
        )

    async def create(self, project: Project) -> Project:
        """持久化新项目。"""

        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project, attribute_names=["workspace"])
        return project

    async def workspace_exists(self, workspace_id: int) -> bool:
        """校验工作空间是否存在且未删除。"""

        total = await self.session.scalar(
            select(func.count(Workspace.id))
            .where(Workspace.id == workspace_id)
            .where(Workspace.deleted_at.is_(None))
        )
        return bool(total)
