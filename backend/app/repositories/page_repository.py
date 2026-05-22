"""文件功能：封装工作空间页面资源库的数据访问逻辑。"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecordStatus
from app.models.page import Page
from app.models.workspace import Project, Workspace, WorkspaceMember
from app.schemas.page import PageListQuery


class PageRepository:
    """页面仓储，负责页面资源的分页查询与持久化。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, query: PageListQuery, *, user_id: int | None = None) -> tuple[list[Page], int]:
        """按统一分页条件返回当前用户可访问页面列表和总数。"""

        statement = (
            select(Page, Project.name.label("project_name"), Workspace.name.label("workspace_name"))
            .where(Page.deleted_at.is_(None))
            .outerjoin(Project, Page.project_id == Project.id)
            .outerjoin(Workspace, Page.workspace_id == Workspace.id)
        )
        count_statement = select(func.count(Page.id)).where(Page.deleted_at.is_(None))
        if user_id is not None:
            access_condition = (
                select(WorkspaceMember.id)
                .where(WorkspaceMember.workspace_id == Page.workspace_id)
                .where(WorkspaceMember.user_id == user_id)
                .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
                .exists()
            )
            statement = statement.where(access_condition)
            count_statement = count_statement.where(access_condition)

        if query.keyword:
            keyword = f"%{query.keyword}%"
            condition = or_(
                Page.code.ilike(keyword),
                Page.page_content.ilike(keyword),
                Page.title.ilike(keyword),
            )
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        if query.status:
            statement = statement.where(Page.status == query.status.value)
            count_statement = count_statement.where(Page.status == query.status.value)
        if query.workspace_id is not None:
            statement = statement.where(Page.workspace_id == query.workspace_id)
            count_statement = count_statement.where(Page.workspace_id == query.workspace_id)
        if query.project_id is not None:
            statement = statement.where(Page.project_id == query.project_id)
            count_statement = count_statement.where(Page.project_id == query.project_id)

        sort_column = getattr(Page, query.sort_by, Page.updated_at)
        sort_expression = sort_column.asc() if query.sort_order == "asc" else sort_column.desc()
        statement = statement.order_by(sort_expression).offset((query.page - 1) * query.page_size).limit(query.page_size)
        total = int(await self.session.scalar(count_statement) or 0)
        result = await self.session.execute(statement)
        
        items = []
        for row in result.all():
            page_obj = row.Page
            # 动态附加关联名称，供 Pydantic model_validate 使用
            page_obj.project_name = row.project_name
            page_obj.workspace_name = row.workspace_name
            items.append(page_obj)
            
        return items, total

    async def get_by_id(self, page_id: int) -> Page | None:
        """按主键查询未删除页面资源，带有关联名称。"""

        statement = (
            select(Page, Project.name.label("project_name"), Workspace.name.label("workspace_name"))
            .where(Page.id == page_id)
            .where(Page.deleted_at.is_(None))
            .outerjoin(Project, Page.project_id == Project.id)
            .outerjoin(Workspace, Page.workspace_id == Workspace.id)
        )
        result = await self.session.execute(statement)
        row = result.first()
        if not row:
            return None
            
        page_obj = row.Page
        page_obj.project_name = row.project_name
        page_obj.workspace_name = row.workspace_name
        return page_obj

    async def get_by_code(self, code: str) -> Page | None:
        """按业务编码查询未删除页面资源。"""

        return await self.session.scalar(
            select(Page).where(Page.code == code).where(Page.deleted_at.is_(None))
        )

    async def create(self, page_model: Page) -> Page:
        """持久化新页面资源。"""

        self.session.add(page_model)
        await self.session.flush()
        return page_model

    async def list_by_ids(self, page_ids: Iterable[int]) -> list[Page]:
        """按主键列表查询未删除页面资源，并保留结果供调用方自行排序。"""

        ids = list(page_ids)
        if not ids:
            return []

        result = await self.session.scalars(
            select(Page).where(Page.id.in_(ids)).where(Page.deleted_at.is_(None))
        )
        return list(result.all())

    async def list_by_codes(self, page_codes: Iterable[str]) -> list[Page]:
        """按业务编码列表查询未删除页面资源，并保留结果供调用方自行排序。"""

        codes = [str(code).strip() for code in page_codes if str(code).strip()]
        if not codes:
            return []

        result = await self.session.scalars(
            select(Page).where(Page.code.in_(codes)).where(Page.deleted_at.is_(None))
        )
        return list(result.all())

    async def list_by_codes_in_workspace(self, workspace_id: int, page_codes: Iterable[str]) -> list[Page]:
        """按工作空间和业务编码列表查询未删除页面资源。"""

        codes = [str(code).strip() for code in page_codes if str(code).strip()]
        if not codes:
            return []

        result = await self.session.scalars(
            select(Page)
            .where(Page.workspace_id == workspace_id)
            .where(Page.code.in_(codes))
            .where(Page.deleted_at.is_(None))
        )
        return list(result.all())
