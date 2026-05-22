"""文件功能：封装页面/组件源码依赖索引的替换、查询与循环检测读取能力。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component_component_dependency import ComponentVersionComponentDependency
from app.models.page_component_dependency import PageVersionComponentDependency


DEPENDENCY_KIND_COMPONENT = "workspace_component"
DEPENDENCY_KIND_RUNTIME_LOCAL = "runtime_local"
DEPENDENCY_KIND_PAGE_MODULE = "page_module"


@dataclass(frozen=True)
class ResolvedComponentDependency:
    """已解析到具体组件版本的源码依赖项。"""

    component_id: int
    component_version_id: int
    component_code: str
    component_version_no: int


class ModuleDependencyRepository:
    """源码依赖索引仓储，负责按版本替换与读取依赖集合。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_page_version_dependencies(
        self,
        *,
        page_id: int,
        page_version_id: int,
        component_dependencies: Iterable[ResolvedComponentDependency],
        runtime_module_paths: Iterable[str],
        page_module_paths: Iterable[str],
    ) -> None:
        """全量替换页面版本依赖索引。"""

        await self.session.execute(
            delete(PageVersionComponentDependency).where(PageVersionComponentDependency.page_version_id == page_version_id)
        )

        rows = [
            PageVersionComponentDependency(
                page_id=page_id,
                page_version_id=page_version_id,
                dependency_kind=DEPENDENCY_KIND_COMPONENT,
                component_id=item.component_id,
                component_version_id=item.component_version_id,
                component_code=item.component_code,
                component_version_no=item.component_version_no,
            )
            for item in sorted(component_dependencies, key=lambda item: (item.component_code, item.component_version_no))
        ]
        rows.extend(
            PageVersionComponentDependency(
                page_id=page_id,
                page_version_id=page_version_id,
                dependency_kind=DEPENDENCY_KIND_RUNTIME_LOCAL,
                runtime_module_path=path,
            )
            for path in sorted(set(runtime_module_paths))
        )
        rows.extend(
            PageVersionComponentDependency(
                page_id=page_id,
                page_version_id=page_version_id,
                dependency_kind=DEPENDENCY_KIND_PAGE_MODULE,
                runtime_module_path=path,
            )
            for path in sorted(set(page_module_paths))
        )
        if rows:
            self.session.add_all(rows)
            await self.session.flush()

    async def replace_component_version_dependencies(
        self,
        *,
        component_id: int,
        component_version_id: int,
        component_dependencies: Iterable[ResolvedComponentDependency],
        runtime_module_paths: Iterable[str],
    ) -> None:
        """全量替换组件版本依赖索引。"""

        await self.session.execute(
            delete(ComponentVersionComponentDependency).where(
                ComponentVersionComponentDependency.component_version_id == component_version_id
            )
        )

        rows = [
            ComponentVersionComponentDependency(
                component_id=component_id,
                component_version_id=component_version_id,
                dependency_kind=DEPENDENCY_KIND_COMPONENT,
                dependency_component_id=item.component_id,
                dependency_component_version_id=item.component_version_id,
                dependency_component_code=item.component_code,
                dependency_component_version_no=item.component_version_no,
            )
            for item in sorted(component_dependencies, key=lambda item: (item.component_code, item.component_version_no))
        ]
        rows.extend(
            ComponentVersionComponentDependency(
                component_id=component_id,
                component_version_id=component_version_id,
                dependency_kind=DEPENDENCY_KIND_RUNTIME_LOCAL,
                runtime_module_path=path,
            )
            for path in sorted(set(runtime_module_paths))
        )
        if rows:
            self.session.add_all(rows)
            await self.session.flush()

    async def list_page_version_dependencies(self, page_version_id: int) -> list[PageVersionComponentDependency]:
        """读取页面版本的源码依赖项。"""

        result = await self.session.scalars(
            select(PageVersionComponentDependency)
            .where(PageVersionComponentDependency.page_version_id == page_version_id)
            .order_by(
                PageVersionComponentDependency.dependency_kind.asc(),
                PageVersionComponentDependency.component_code.asc(),
                PageVersionComponentDependency.component_version_no.asc(),
                PageVersionComponentDependency.runtime_module_path.asc(),
            )
        )
        return list(result.all())

    async def list_component_version_dependencies(self, component_version_id: int) -> list[ComponentVersionComponentDependency]:
        """读取组件版本的源码依赖项。"""

        result = await self.session.scalars(
            select(ComponentVersionComponentDependency)
            .where(ComponentVersionComponentDependency.component_version_id == component_version_id)
            .order_by(
                ComponentVersionComponentDependency.dependency_kind.asc(),
                ComponentVersionComponentDependency.dependency_component_code.asc(),
                ComponentVersionComponentDependency.dependency_component_version_no.asc(),
                ComponentVersionComponentDependency.runtime_module_path.asc(),
            )
        )
        return list(result.all())

    async def list_component_dependency_version_ids(self, component_version_id: int) -> list[int]:
        """读取组件版本依赖的其他组件版本主键。"""

        result = await self.session.scalars(
            select(ComponentVersionComponentDependency.dependency_component_version_id)
            .where(ComponentVersionComponentDependency.component_version_id == component_version_id)
            .where(ComponentVersionComponentDependency.dependency_kind == DEPENDENCY_KIND_COMPONENT)
            .where(ComponentVersionComponentDependency.dependency_component_version_id.is_not(None))
        )
        return [int(item) for item in result.all()]
