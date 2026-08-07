"""文件功能：封装项目实体的数据访问逻辑。"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import ProjectRouteType, RecordStatus
from app.models.page import Page
from app.models.project_route import ProjectRoute
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
            condition = or_(
                Project.name.ilike(keyword),
                Project.code.ilike(keyword),
                Project.description.ilike(keyword),
            )
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

    async def list_cover_pages(self, project_ids: list[int]) -> dict[int, Page]:
        """按首个可见路由页面优先、页面编码升序兜底的规则读取项目封面页。"""

        if not project_ids:
            return {}

        routes = list(await self.session.scalars(
            select(ProjectRoute)
            .where(ProjectRoute.project_id.in_(project_ids))
            .order_by(ProjectRoute.project_id.asc(), ProjectRoute.order.asc(), ProjectRoute.id.asc())
        ))
        route_page_ids = [route.page_id for route in routes if route.page_id is not None]
        route_pages = list(await self.session.scalars(
            select(Page)
            .where(Page.id.in_(route_page_ids))
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(Page.deleted_at.is_(None))
        )) if route_page_ids else []
        route_page_by_id = {page.id: page for page in route_pages}

        ranked_fallback_ids = (
            select(
                Page.id.label("page_id"),
                func.row_number().over(
                    partition_by=Page.project_id,
                    order_by=(Page.code.asc(), Page.id.asc()),
                ).label("page_rank"),
            )
            .where(Page.project_id.in_(project_ids))
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(Page.deleted_at.is_(None))
            .subquery()
        )
        fallback_pages = list(await self.session.scalars(
            select(Page)
            .join(ranked_fallback_ids, Page.id == ranked_fallback_ids.c.page_id)
            .where(ranked_fallback_ids.c.page_rank == 1)
        ))
        fallback_by_project = {
            int(page.project_id): page
            for page in fallback_pages
            if page.project_id is not None
        }

        roots_by_project: dict[int, list[ProjectRoute]] = defaultdict(list)
        children_by_parent: dict[int, list[ProjectRoute]] = defaultdict(list)
        for route in routes:
            if route.parent_id is None:
                roots_by_project[route.project_id].append(route)
            else:
                children_by_parent[route.parent_id].append(route)

        cover_pages: dict[int, Page] = {}
        for project_id in project_ids:
            for root in self._sort_routes(roots_by_project.get(project_id, [])):
                if root.hidden:
                    continue
                if root.route_type == ProjectRouteType.PAGE.value:
                    page = route_page_by_id.get(root.page_id)
                    if page is not None and page.project_id == project_id:
                        cover_pages[project_id] = page
                        break
                    continue
                for child in self._sort_routes(children_by_parent.get(root.id, [])):
                    page = route_page_by_id.get(child.page_id)
                    if not child.hidden and page is not None and page.project_id == project_id:
                        cover_pages[project_id] = page
                        break
                if project_id in cover_pages:
                    break

            if project_id not in cover_pages and project_id in fallback_by_project:
                cover_pages[project_id] = fallback_by_project[project_id]

        return cover_pages

    async def list_page_counts(self, project_ids: list[int]) -> dict[int, tuple[int, int]]:
        """批量统计项目下启用页面总数和已加入路由的去重页面数。"""

        if not project_ids:
            return {}

        result = await self.session.execute(
            select(
                Page.project_id,
                func.count(func.distinct(Page.id)).label("total_page_count"),
                func.count(func.distinct(ProjectRoute.page_id)).label("routed_page_count"),
            )
            .outerjoin(
                ProjectRoute,
                (ProjectRoute.project_id == Page.project_id) & (ProjectRoute.page_id == Page.id),
            )
            .where(Page.project_id.in_(project_ids))
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(Page.deleted_at.is_(None))
            .group_by(Page.project_id)
        )
        return {
            int(row.project_id): (int(row.routed_page_count or 0), int(row.total_page_count or 0))
            for row in result.all()
            if row.project_id is not None
        }

    @staticmethod
    def _sort_routes(routes: list[ProjectRoute]) -> list[ProjectRoute]:
        """按路由显式顺序和主键稳定排序同级节点。"""

        return sorted(routes, key=lambda route: (route.order, route.id))

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
