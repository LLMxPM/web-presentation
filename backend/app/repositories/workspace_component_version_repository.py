"""文件功能：封装工作空间组件版本实体的数据访问逻辑。"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_component_version import WorkspaceComponentVersion


class WorkspaceComponentVersionRepository:
    """工作空间组件版本仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, version: WorkspaceComponentVersion) -> WorkspaceComponentVersion:
        """持久化新组件版本。"""

        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_component_and_version(self, component_id: int, version_no: int) -> WorkspaceComponentVersion | None:
        """按组件和版本号读取版本快照。"""

        return await self.session.scalar(
            select(WorkspaceComponentVersion)
            .where(WorkspaceComponentVersion.component_id == component_id)
            .where(WorkspaceComponentVersion.version_no == version_no)
        )

    async def get_by_id(self, version_id: int) -> WorkspaceComponentVersion | None:
        """按版本主键读取版本快照。"""

        return await self.session.scalar(
            select(WorkspaceComponentVersion).where(WorkspaceComponentVersion.id == version_id)
        )

    async def list_by_component_id(self, component_id: int, descending: bool = True) -> list[WorkspaceComponentVersion]:
        """按组件读取全部版本。"""

        statement = select(WorkspaceComponentVersion).where(WorkspaceComponentVersion.component_id == component_id)
        order_column = WorkspaceComponentVersion.version_no.desc() if descending else WorkspaceComponentVersion.version_no.asc()
        result = await self.session.scalars(statement.order_by(order_column))
        return list(result.all())

    async def list_by_ids(self, version_ids: Iterable[int]) -> list[WorkspaceComponentVersion]:
        """按版本主键批量读取版本快照。"""

        ids = [int(version_id) for version_id in version_ids]
        if not ids:
            return []

        result = await self.session.scalars(
            select(WorkspaceComponentVersion).where(WorkspaceComponentVersion.id.in_(ids))
        )
        return list(result.all())
