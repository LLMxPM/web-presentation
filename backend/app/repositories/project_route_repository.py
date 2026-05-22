"""文件功能：封装项目路由树节点的查询、清空与创建逻辑。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_route import ProjectRoute


class ProjectRouteRepository:
    """项目路由仓储，负责项目路由树的结构化持久化。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_project(self, project_id: int) -> list[ProjectRoute]:
        """按项目读取全部路由节点，供服务层重建路由树。"""

        result = await self.session.scalars(
            select(ProjectRoute)
            .where(ProjectRoute.project_id == project_id)
            .order_by(ProjectRoute.parent_id.asc().nullsfirst(), ProjectRoute.order.asc(), ProjectRoute.id.asc())
        )
        return list(result.all())

    async def delete_by_project(self, project_id: int) -> None:
        """清空指定项目下的全部路由节点。"""

        await self.session.execute(delete(ProjectRoute).where(ProjectRoute.project_id == project_id))

    async def delete_page_bindings(self, project_id: int, page_id: int) -> None:
        """删除指定项目内绑定某个页面的全部路由节点。"""

        await self.session.execute(
            delete(ProjectRoute)
            .where(ProjectRoute.project_id == project_id)
            .where(ProjectRoute.page_id == page_id)
        )

    async def delete_by_ids(self, route_ids: list[int]) -> None:
        """按主键批量删除项目路由节点。"""

        if not route_ids:
            return
        await self.session.execute(delete(ProjectRoute).where(ProjectRoute.id.in_(route_ids)))

    async def create(self, route: ProjectRoute) -> ProjectRoute:
        """创建单个路由节点并立即刷新主键。"""

        self.session.add(route)
        await self.session.flush()
        return route
