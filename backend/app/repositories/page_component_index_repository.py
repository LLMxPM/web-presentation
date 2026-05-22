"""文件功能：封装页面组件索引的数据访问逻辑，提供按版本重建与查询能力。"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.page_component_resource import PageVersionComponentResource
from app.models.page_component_usage import PageVersionComponentUsage


class PageComponentIndexRepository:
    """页面组件索引仓储，负责版本级索引写入与读取。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_version(
        self,
        *,
        project_id: int | None,
        page_id: int,
        page_version_id: int,
        component_names: Iterable[str],
        resource_names: Iterable[tuple[str, str]],
    ) -> None:
        """按页面版本全量替换组件索引，确保重复执行结果幂等。"""

        await self.session.execute(
            delete(PageVersionComponentUsage).where(PageVersionComponentUsage.page_version_id == page_version_id)
        )
        await self.session.execute(
            delete(PageVersionComponentResource).where(PageVersionComponentResource.page_version_id == page_version_id)
        )

        component_name_list = sorted(set(component_names))
        if component_name_list:
            self.session.add_all(
                [
                    PageVersionComponentUsage(
                        project_id=project_id,
                        page_id=page_id,
                        page_version_id=page_version_id,
                        component_name=component_name,
                    )
                    for component_name in component_name_list
                ]
            )

        resource_name_list = sorted(set(resource_names))
        if resource_name_list:
            self.session.add_all(
                [
                    PageVersionComponentResource(
                        project_id=project_id,
                        page_id=page_id,
                        page_version_id=page_version_id,
                        component_name=component_name,
                        resource_attr="name",
                        resource_name=resource_name,
                    )
                    for component_name, resource_name in resource_name_list
                ]
            )

        await self.session.flush()

    async def list_component_usages_by_version(self, page_version_id: int) -> list[PageVersionComponentUsage]:
        """按页面版本读取组件使用统计，供调试和测试断言。"""

        result = await self.session.scalars(
            select(PageVersionComponentUsage)
            .where(PageVersionComponentUsage.page_version_id == page_version_id)
            .order_by(PageVersionComponentUsage.component_name.asc())
        )
        return list(result.all())

    async def list_component_resources_by_version(self, page_version_id: int) -> list[PageVersionComponentResource]:
        """按页面版本读取组件资源参数统计，供调试和测试断言。"""

        result = await self.session.scalars(
            select(PageVersionComponentResource)
            .where(PageVersionComponentResource.page_version_id == page_version_id)
            .order_by(
                PageVersionComponentResource.component_name.asc(),
                PageVersionComponentResource.resource_name.asc(),
            )
        )
        return list(result.all())
