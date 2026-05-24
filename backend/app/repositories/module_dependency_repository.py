"""文件功能：封装页面/组件源码依赖索引的替换、查询与循环检测读取能力。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_module_policy import RuntimeKitImportDependency
from app.models.component_component_dependency import ComponentVersionComponentDependency
from app.models.enums import RecordStatus
from app.models.page import Page
from app.models.page_component_dependency import PageVersionComponentDependency
from app.models.page_version import PageVersion
from app.models.workspace import Project
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion


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


@dataclass(frozen=True)
class PageComponentReferenceRow:
    """当前页面版本对指定组件的直接引用行。"""

    page_id: int
    page_code: str
    page_title: str
    project_id: int | None
    project_name: str | None
    current_version_no: int
    page_version_id: int
    referenced_component_version_no: int


@dataclass(frozen=True)
class ComponentComponentReferenceRow:
    """当前组件发布版本对指定组件的直接引用行。"""

    component_id: int
    component_code: str
    component_name: str
    current_version_no: int
    component_version_id: int
    referenced_component_version_no: int


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
        runtime_module_paths: Iterable[RuntimeKitImportDependency],
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
                runtime_module_path=item.import_path,
                runtime_kit_name=item.name,
                runtime_kit_base_name=item.base_name,
                runtime_kit_version_no=item.version_no,
                runtime_kit_import_path=item.import_path,
            )
            for item in sorted(runtime_module_paths, key=lambda item: item.import_path)
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
        runtime_module_paths: Iterable[RuntimeKitImportDependency],
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
                runtime_module_path=item.import_path,
                runtime_kit_name=item.name,
                runtime_kit_base_name=item.base_name,
                runtime_kit_version_no=item.version_no,
                runtime_kit_import_path=item.import_path,
            )
            for item in sorted(runtime_module_paths, key=lambda item: item.import_path)
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

    async def list_current_page_references_to_component(self, component_id: int) -> list[PageComponentReferenceRow]:
        """读取当前页面版本中直接引用指定组件的依赖索引。"""

        result = await self.session.execute(
            select(
                Page.id.label("page_id"),
                Page.code.label("page_code"),
                Page.title.label("page_title"),
                Page.project_id.label("project_id"),
                Project.name.label("project_name"),
                Page.current_version_no.label("current_version_no"),
                PageVersion.id.label("page_version_id"),
                PageVersionComponentDependency.component_version_no.label("referenced_component_version_no"),
            )
            .join(Page, PageVersionComponentDependency.page_id == Page.id)
            .join(PageVersion, PageVersionComponentDependency.page_version_id == PageVersion.id)
            .outerjoin(Project, Page.project_id == Project.id)
            .where(PageVersionComponentDependency.dependency_kind == DEPENDENCY_KIND_COMPONENT)
            .where(PageVersionComponentDependency.component_id == component_id)
            .where(PageVersion.version_no == Page.current_version_no)
            .where(Page.status == RecordStatus.ACTIVE.value)
            .where(or_(Page.project_id.is_(None), Project.status == RecordStatus.ACTIVE.value))
            .where(Page.deleted_at.is_(None))
            .order_by(Project.name.asc(), Page.title.asc(), Page.code.asc())
        )
        return [
            PageComponentReferenceRow(
                page_id=int(row.page_id),
                page_code=str(row.page_code),
                page_title=str(row.page_title),
                project_id=row.project_id,
                project_name=row.project_name,
                current_version_no=int(row.current_version_no),
                page_version_id=int(row.page_version_id),
                referenced_component_version_no=int(row.referenced_component_version_no),
            )
            for row in result.all()
            if row.referenced_component_version_no is not None
        ]

    async def list_current_component_references_to_component(
        self,
        component_id: int,
    ) -> list[ComponentComponentReferenceRow]:
        """读取当前组件发布版本中直接引用指定组件的依赖索引。"""

        result = await self.session.execute(
            select(
                WorkspaceComponent.id.label("component_id"),
                WorkspaceComponent.code.label("component_code"),
                WorkspaceComponent.name.label("component_name"),
                WorkspaceComponent.current_version_no.label("current_version_no"),
                WorkspaceComponentVersion.id.label("component_version_id"),
                ComponentVersionComponentDependency.dependency_component_version_no.label(
                    "referenced_component_version_no"
                ),
            )
            .join(WorkspaceComponent, ComponentVersionComponentDependency.component_id == WorkspaceComponent.id)
            .join(
                WorkspaceComponentVersion,
                ComponentVersionComponentDependency.component_version_id == WorkspaceComponentVersion.id,
            )
            .where(ComponentVersionComponentDependency.dependency_kind == DEPENDENCY_KIND_COMPONENT)
            .where(ComponentVersionComponentDependency.dependency_component_id == component_id)
            .where(WorkspaceComponentVersion.version_no == WorkspaceComponent.current_version_no)
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .order_by(WorkspaceComponent.name.asc(), WorkspaceComponent.code.asc())
        )
        return [
            ComponentComponentReferenceRow(
                component_id=int(row.component_id),
                component_code=str(row.component_code),
                component_name=str(row.component_name),
                current_version_no=int(row.current_version_no),
                component_version_id=int(row.component_version_id),
                referenced_component_version_no=int(row.referenced_component_version_no),
            )
            for row in result.all()
            if row.referenced_component_version_no is not None
        ]
