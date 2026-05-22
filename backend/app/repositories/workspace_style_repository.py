"""文件功能：封装工作空间样式库的数据访问逻辑。"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_style import WorkspaceStyle
from app.schemas.common import ListQuery


class WorkspaceStyleRepository:
    """工作空间样式仓储，负责样式列表与基础查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, workspace_id: int, query: ListQuery | None = None) -> tuple[list[WorkspaceStyle], int]:
        """按工作空间与分页条件返回样式列表。"""

        statement = (
            select(WorkspaceStyle)
            .where(WorkspaceStyle.workspace_id == workspace_id)
            .where(WorkspaceStyle.deleted_at.is_(None))
        )
        count_statement = (
            select(func.count(WorkspaceStyle.id))
            .where(WorkspaceStyle.workspace_id == workspace_id)
            .where(WorkspaceStyle.deleted_at.is_(None))
        )

        if query is not None and query.keyword:
            keyword = f"%{query.keyword}%"
            condition = or_(
                WorkspaceStyle.name.ilike(keyword),
                WorkspaceStyle.key.ilike(keyword),
                WorkspaceStyle.description.ilike(keyword),
            )
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

        sort_by = query.sort_by if query is not None else "updated_at"
        sort_order = query.sort_order if query is not None else "desc"
        sort_column = getattr(WorkspaceStyle, sort_by, WorkspaceStyle.updated_at)
        sort_expression = sort_column.asc() if sort_order == "asc" else sort_column.desc()
        statement = statement.order_by(sort_expression)

        if query is not None:
            statement = statement.offset((query.page - 1) * query.page_size).limit(query.page_size)

        total = int(await self.session.scalar(count_statement) or 0)
        result = await self.session.scalars(statement)
        return list(result), total

    async def get_by_id(self, workspace_id: int, style_id: int) -> WorkspaceStyle | None:
        """按主键获取工作空间样式。"""

        return await self.session.scalar(
            select(WorkspaceStyle)
            .where(WorkspaceStyle.workspace_id == workspace_id)
            .where(WorkspaceStyle.id == style_id)
            .where(WorkspaceStyle.deleted_at.is_(None))
        )

    async def get_by_key(self, workspace_id: int, key: str) -> WorkspaceStyle | None:
        """按 key 获取工作空间样式。"""

        return await self.session.scalar(
            select(WorkspaceStyle)
            .where(WorkspaceStyle.workspace_id == workspace_id)
            .where(WorkspaceStyle.key == key)
            .where(WorkspaceStyle.deleted_at.is_(None))
        )

    async def create(self, style: WorkspaceStyle) -> WorkspaceStyle:
        """持久化样式实体。"""

        self.session.add(style)
        await self.session.flush()
        return style
