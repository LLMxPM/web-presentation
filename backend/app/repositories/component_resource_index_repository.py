"""文件功能：封装组件版本资源参数索引的数据访问逻辑。"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component_resource import ComponentVersionComponentResource


class ComponentResourceIndexRepository:
    """组件资源索引仓储，负责发布版本资源名集合的写入与查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_version(
        self,
        *,
        workspace_id: int,
        component_id: int,
        component_version_id: int,
        resource_names: Iterable[tuple[str, str]],
    ) -> None:
        """按组件发布版本全量替换资源索引，确保重复执行幂等。"""

        await self.session.execute(
            delete(ComponentVersionComponentResource).where(
                ComponentVersionComponentResource.component_version_id == component_version_id
            )
        )

        resource_name_list = sorted(set(resource_names))
        if resource_name_list:
            self.session.add_all(
                [
                    ComponentVersionComponentResource(
                        workspace_id=workspace_id,
                        component_id=component_id,
                        component_version_id=component_version_id,
                        component_name=component_name,
                        resource_attr="name",
                        resource_name=resource_name,
                    )
                    for component_name, resource_name in resource_name_list
                ]
            )

        await self.session.flush()

    async def list_component_resources_by_version(
        self,
        component_version_id: int,
    ) -> list[ComponentVersionComponentResource]:
        """读取指定组件版本的资源索引集合。"""

        result = await self.session.scalars(
            select(ComponentVersionComponentResource)
            .where(ComponentVersionComponentResource.component_version_id == component_version_id)
            .order_by(
                ComponentVersionComponentResource.component_name.asc(),
                ComponentVersionComponentResource.resource_name.asc(),
            )
        )
        return list(result.all())

    async def list_component_version_ids_by_resource_name(self, workspace_id: int, resource_name: str) -> list[int]:
        """按工作空间和资源名反查引用该资源的组件版本 ID。"""

        result = await self.session.scalars(
            select(ComponentVersionComponentResource.component_version_id)
            .where(ComponentVersionComponentResource.workspace_id == workspace_id)
            .where(ComponentVersionComponentResource.resource_name == resource_name)
        )
        return list(dict.fromkeys(int(item) for item in result.all()))
