"""文件功能：封装工作空间主题库的数据访问逻辑。"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_theme import WorkspaceTheme
from app.schemas.common import ListQuery


class WorkspaceThemeRepository:
    """工作空间主题仓储，负责主题列表与基础查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, workspace_id: int, query: ListQuery | None = None) -> tuple[list[WorkspaceTheme], int]:
        """按工作空间与分页条件返回主题列表。"""

        statement = (
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.deleted_at.is_(None))
        )
        count_statement = (
            select(func.count(WorkspaceTheme.id))
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.deleted_at.is_(None))
        )

        if query is not None and query.keyword:
            keyword = f"%{query.keyword}%"
            condition = or_(WorkspaceTheme.name.ilike(keyword), WorkspaceTheme.key.ilike(keyword))
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        sort_by = query.sort_by if query is not None else "updated_at"
        sort_order = query.sort_order if query is not None else "desc"
        sort_column = getattr(WorkspaceTheme, sort_by, WorkspaceTheme.updated_at)
        sort_expression = sort_column.asc() if sort_order == "asc" else sort_column.desc()
        statement = statement.order_by(sort_expression)

        if query is not None:
            statement = statement.offset((query.page - 1) * query.page_size).limit(query.page_size)

        total = int(await self.session.scalar(count_statement) or 0)
        result = await self.session.scalars(statement)
        return list(result), total

    async def list_by_workspace(self, workspace_id: int) -> list[WorkspaceTheme]:
        """返回工作空间全部未删除主题。"""

        result = await self.session.scalars(
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.deleted_at.is_(None))
            .order_by(WorkspaceTheme.updated_at.desc(), WorkspaceTheme.id.desc())
        )
        return list(result)

    async def get_by_id(self, workspace_id: int, theme_id: int) -> WorkspaceTheme | None:
        """按主键获取工作空间主题。"""

        return await self.session.scalar(
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.id == theme_id)
            .where(WorkspaceTheme.deleted_at.is_(None))
        )

    async def get_by_key(self, workspace_id: int, key: str) -> WorkspaceTheme | None:
        """按 key 获取工作空间主题。"""

        return await self.session.scalar(
            select(WorkspaceTheme)
            .where(WorkspaceTheme.workspace_id == workspace_id)
            .where(WorkspaceTheme.key == key)
            .where(WorkspaceTheme.deleted_at.is_(None))
        )

    async def create(self, theme: WorkspaceTheme) -> WorkspaceTheme:
        """持久化主题实体。"""

        self.session.add(theme)
        await self.session.flush()
        return theme
