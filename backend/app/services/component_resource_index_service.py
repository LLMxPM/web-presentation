"""文件功能：解析并维护组件发布版本的资源参数索引。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.component_resource_index_repository import ComponentResourceIndexRepository
from app.services.resource_reference_parser import ResourceReferenceParser


class ComponentResourceIndexService:
    """组件资源索引服务，负责发布版本资源引用的解析、写入与读取。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ComponentResourceIndexRepository(session)

    async def rebuild_component_version_index(
        self,
        *,
        component: WorkspaceComponent,
        component_version: WorkspaceComponentVersion,
    ) -> None:
        """按组件发布版本全量重建资源索引。"""

        resource_names = self.collect_version_resource_items(
            content=component_version.content,
            preview_schema=component_version.preview_schema,
        )
        await self.repository.replace_for_version(
            workspace_id=component.workspace_id,
            component_id=component.id,
            component_version_id=component_version.id,
            resource_names=resource_names,
        )

    async def list_resource_items_by_version(self, component_version_id: int):
        """读取指定组件版本的资源索引集合。"""

        return await self.repository.list_component_resources_by_version(component_version_id)

    @staticmethod
    def collect_version_resource_items(
        *,
        content: str,
        preview_schema: str | None,
    ) -> set[tuple[str, str]]:
        """从组件源码和 preview_schema 中收集资源组件名与资源名。"""

        resource_items: set[tuple[str, str]] = set()
        _, template_resource_items = ResourceReferenceParser.collect_vue_component_index(content or "")
        resource_items.update(template_resource_items)

        for asset_name in ResourceReferenceParser.collect_static_asset_call_names([content or ""]):
            resource_items.add(("AssetHelper", asset_name))

        schema_result = ResourceReferenceParser.collect_preview_schema_asset_references(preview_schema)
        for asset_name in schema_result.asset_names:
            resource_items.add(("PreviewSchema", asset_name))
        if schema_result.has_dynamic:
            resource_items.add(("PreviewSchema", "__DYNAMIC__"))

        return resource_items
