"""文件功能：封装页面版本链的数据访问逻辑，提供版本查询与持久化能力。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.page_version import PageVersion


class PageVersionRepository:
    """页面版本仓储，负责版本链的增删查改与顺序读取。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, version_model: PageVersion) -> PageVersion:
        """持久化一个页面版本节点，并在当前事务内返回该对象。"""

        self.session.add(version_model)
        await self.session.flush()
        return version_model

    async def get_by_page_and_version(self, page_id: int, version_no: int) -> PageVersion | None:
        """按页面与版本号读取单个版本节点。"""

        return await self.session.scalar(
            select(PageVersion)
            .where(PageVersion.page_id == page_id)
            .where(PageVersion.version_no == version_no)
        )

    async def get_latest_by_page_id(self, page_id: int) -> PageVersion | None:
        """读取页面当前最新版本节点。"""

        return await self.session.scalar(
            select(PageVersion)
            .where(PageVersion.page_id == page_id)
            .order_by(PageVersion.version_no.desc())
            .limit(1)
        )

    async def list_by_page_id(self, page_id: int, descending: bool = True) -> list[PageVersion]:
        """按版本号顺序列出页面的完整版本链。"""

        order_by = PageVersion.version_no.desc() if descending else PageVersion.version_no.asc()
        result = await self.session.scalars(
            select(PageVersion)
            .where(PageVersion.page_id == page_id)
            .order_by(order_by)
        )
        return list(result.all())
