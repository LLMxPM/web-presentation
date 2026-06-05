"""文件功能：维护样式建议组件与项目建议组件快照，并为 AI 工具提供受控摘要。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.enums import RecordStatus, WorkspaceComponentType
from app.models.project_suggested_component import ProjectSuggestedComponent
from app.models.workspace import Project
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_style import WorkspaceStyle
from app.models.workspace_style_suggested_component import WorkspaceStyleSuggestedComponent
from app.repositories.project_repository import ProjectRepository
from app.repositories.workspace_style_repository import WorkspaceStyleRepository
from app.schemas.component import SuggestedComponentItem


class SuggestedComponentService:
    """建议组件服务，统一处理样式关联、项目快照、排序和组件可用性校验。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_repository = ProjectRepository(session)
        self.style_repository = WorkspaceStyleRepository(session)

    async def list_style_component_items(
        self,
        workspace_id: int,
        style_id: int,
        *,
        include_unavailable: bool = False,
    ) -> list[SuggestedComponentItem]:
        """读取样式建议组件摘要，按维护顺序返回。"""

        if include_unavailable:
            return await self._list_style_component_items_for_management(workspace_id, style_id)
        components = await self.list_style_components(workspace_id, style_id)
        return [self.dump_component_item(component) for component in components]

    async def ensure_style_in_workspace(self, workspace_id: int, style_id: int) -> None:
        """校验样式存在且属于指定工作空间。"""

        await self._get_style_or_raise(workspace_id, style_id)

    async def list_project_component_items(
        self,
        project_id: int,
        *,
        workspace_id: int | None = None,
        include_unavailable: bool = False,
    ) -> list[SuggestedComponentItem]:
        """读取项目建议组件快照摘要，按项目保存顺序返回。"""

        if include_unavailable:
            return await self._list_project_component_items_for_management(project_id, workspace_id=workspace_id)
        components = await self.list_project_components(project_id, workspace_id=workspace_id)
        return [self.dump_component_item(component) for component in components]

    async def _list_style_component_items_for_management(
        self,
        workspace_id: int,
        style_id: int,
    ) -> list[SuggestedComponentItem]:
        """读取样式管理界面使用的建议组件摘要，保留已失效组件并标注原因。"""

        await self._get_style_or_raise(workspace_id, style_id)
        statement = (
            select(WorkspaceComponent)
            .join(WorkspaceStyleSuggestedComponent, WorkspaceStyleSuggestedComponent.component_id == WorkspaceComponent.id)
            .where(WorkspaceStyleSuggestedComponent.style_id == style_id)
            .order_by(WorkspaceStyleSuggestedComponent.sort_order.asc(), WorkspaceStyleSuggestedComponent.id.asc())
        )
        components = list((await self.session.execute(statement)).scalars().all())
        return [self.dump_component_item_for_management(component, workspace_id) for component in components]

    async def _list_project_component_items_for_management(
        self,
        project_id: int,
        *,
        workspace_id: int | None = None,
    ) -> list[SuggestedComponentItem]:
        """读取项目管理界面使用的建议组件摘要，保留已失效组件并标注原因。"""

        project = await self._get_project_or_raise(project_id, workspace_id=workspace_id)
        statement = (
            select(WorkspaceComponent)
            .join(ProjectSuggestedComponent, ProjectSuggestedComponent.component_id == WorkspaceComponent.id)
            .where(ProjectSuggestedComponent.project_id == project_id)
            .order_by(ProjectSuggestedComponent.sort_order.asc(), ProjectSuggestedComponent.id.asc())
        )
        components = list((await self.session.execute(statement)).scalars().all())
        return [self.dump_component_item_for_management(component, project.workspace_id) for component in components]

    async def list_style_components(self, workspace_id: int, style_id: int) -> list[WorkspaceComponent]:
        """读取样式关联的有效已发布组件模型列表。"""

        await self._get_style_or_raise(workspace_id, style_id)
        statement = (
            select(WorkspaceComponent)
            .join(WorkspaceStyleSuggestedComponent, WorkspaceStyleSuggestedComponent.component_id == WorkspaceComponent.id)
            .where(WorkspaceStyleSuggestedComponent.style_id == style_id)
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.current_version_no > 0)
            .order_by(WorkspaceStyleSuggestedComponent.sort_order.asc(), WorkspaceStyleSuggestedComponent.id.asc())
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def list_project_components(
        self,
        project_id: int,
        *,
        workspace_id: int | None = None,
    ) -> list[WorkspaceComponent]:
        """读取项目快照中的有效已发布组件模型列表。"""

        project = await self._get_project_or_raise(project_id, workspace_id=workspace_id)
        statement = (
            select(WorkspaceComponent)
            .join(ProjectSuggestedComponent, ProjectSuggestedComponent.component_id == WorkspaceComponent.id)
            .where(ProjectSuggestedComponent.project_id == project_id)
            .where(WorkspaceComponent.workspace_id == project.workspace_id)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.current_version_no > 0)
            .order_by(ProjectSuggestedComponent.sort_order.asc(), ProjectSuggestedComponent.id.asc())
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def replace_style_components(
        self,
        workspace_id: int,
        style_id: int,
        component_ids: list[int],
        *,
        commit: bool = True,
    ) -> list[SuggestedComponentItem]:
        """覆盖保存样式建议组件，校验组件属于当前工作空间且已发布。"""

        await self._get_style_or_raise(workspace_id, style_id)
        normalized_component_ids = self._normalize_component_ids(component_ids)
        components_by_id = await self._load_suggestible_components_by_id(
            workspace_id,
            normalized_component_ids,
            invalid_code="WORKSPACE_STYLE_SUGGESTED_COMPONENT_INVALID",
        )
        ordered_components = [components_by_id[component_id] for component_id in normalized_component_ids]

        await self._delete_style_links(style_id)
        for index, component in enumerate(ordered_components):
            self.session.add(
                WorkspaceStyleSuggestedComponent(
                    style_id=style_id,
                    component_id=component.id,
                    sort_order=index * 10,
                )
            )
        if commit:
            await self.session.commit()
        return [self.dump_component_item(component) for component in ordered_components]

    async def replace_project_components(
        self,
        project_id: int,
        component_ids: list[int],
        *,
        commit: bool = True,
    ) -> list[SuggestedComponentItem]:
        """覆盖保存项目建议组件快照，校验组件属于项目工作空间且已发布。"""

        project = await self._get_project_or_raise(project_id)
        normalized_component_ids = self._normalize_component_ids(component_ids)
        components_by_id = await self._load_suggestible_components_by_id(
            project.workspace_id,
            normalized_component_ids,
            invalid_code="PROJECT_SUGGESTED_COMPONENT_INVALID",
        )
        ordered_components = [components_by_id[component_id] for component_id in normalized_component_ids]
        await self._replace_project_components_with_models(project_id, ordered_components)
        if commit:
            await self.session.commit()
        return [self.dump_component_item(component) for component in ordered_components]

    async def copy_style_components_to_project(
        self,
        project_id: int,
        source_style_id: int,
        *,
        workspace_id: int | None = None,
        commit: bool = True,
    ) -> list[SuggestedComponentItem]:
        """把样式建议组件复制为项目快照，不建立项目到样式的持久关联。"""

        project = await self._get_project_or_raise(project_id, workspace_id=workspace_id)
        await self._get_style_or_raise(project.workspace_id, source_style_id)
        components = await self.list_style_components(project.workspace_id, source_style_id)
        await self._replace_project_components_with_models(project.id, components)
        if commit:
            await self.session.commit()
        return [self.dump_component_item(component) for component in components]

    async def copy_style_components(
        self,
        workspace_id: int,
        *,
        source_style_id: int,
        target_style_id: int,
        commit: bool = True,
    ) -> list[SuggestedComponentItem]:
        """复制样式建议组件到另一个样式，供样式复制功能复用。"""

        await self._get_style_or_raise(workspace_id, target_style_id)
        components = await self.list_style_components(workspace_id, source_style_id)
        await self._delete_style_links(target_style_id)
        for index, component in enumerate(components):
            self.session.add(
                WorkspaceStyleSuggestedComponent(
                    style_id=target_style_id,
                    component_id=component.id,
                    sort_order=index * 10,
                )
            )
        if commit:
            await self.session.commit()
        return [self.dump_component_item(component) for component in components]

    async def clear_project_components(self, project_id: int, *, commit: bool = True) -> None:
        """清空项目建议组件快照；项目迁移工作空间时使用。"""

        await self._delete_project_links(project_id)
        if commit:
            await self.session.commit()

    async def clear_style_components(self, style_id: int, *, commit: bool = True) -> None:
        """清空样式建议组件关联；删除样式前显式调用。"""

        await self._delete_style_links(style_id)
        if commit:
            await self.session.commit()

    async def find_package_component_ids(self, workspace_id: int, component_summaries: list[dict[str, Any]]) -> list[int]:
        """按离线包中的组件摘要在目标工作空间中尽力匹配已有已发布组件。"""

        matched_ids: list[int] = []
        seen_ids: set[int] = set()
        for summary in component_summaries:
            component = await self._find_package_component(workspace_id, summary)
            if component is None or component.id in seen_ids:
                continue
            seen_ids.add(component.id)
            matched_ids.append(component.id)
        return matched_ids

    async def _replace_project_components_with_models(self, project_id: int, components: list[WorkspaceComponent]) -> None:
        """用指定组件模型覆盖项目建议组件快照。"""

        await self._delete_project_links(project_id)
        for index, component in enumerate(components):
            self.session.add(
                ProjectSuggestedComponent(
                    project_id=project_id,
                    component_id=component.id,
                    sort_order=index * 10,
                )
            )

    async def _load_suggestible_components_by_id(
        self,
        workspace_id: int,
        component_ids: list[int],
        *,
        invalid_code: str,
    ) -> dict[int, WorkspaceComponent]:
        """批量读取可作为建议组件的组件，并确保请求中的每个组件都有效。"""

        if not component_ids:
            return {}
        statement = (
            select(WorkspaceComponent)
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.id.in_(component_ids))
            .where(WorkspaceComponent.deleted_at.is_(None))
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.current_version_no > 0)
        )
        components = list((await self.session.execute(statement)).scalars().all())
        components_by_id = {component.id: component for component in components}
        missing_ids = [component_id for component_id in component_ids if component_id not in components_by_id]
        if missing_ids:
            raise AppException(
                status_code=400,
                code=invalid_code,
                detail="建议组件必须属于同一工作空间，且为 active 的已发布组件。",
            )
        return components_by_id

    async def _find_package_component(self, workspace_id: int, summary: dict[str, Any]) -> WorkspaceComponent | None:
        """根据离线包组件摘要匹配目标工作空间已有已发布组件。"""

        code = str(summary.get("code") or "").strip()
        import_name = str(summary.get("import_name") or "").strip()
        name = str(summary.get("name") or "").strip()
        component_type = str(summary.get("component_type") or "").strip()
        conditions = []
        if code:
            conditions.append(WorkspaceComponent.code == code)
        if import_name:
            conditions.append(WorkspaceComponent.import_name == import_name)
        if name and component_type:
            conditions.append(
                (WorkspaceComponent.name == name)
                & (WorkspaceComponent.component_type == component_type)
            )
        if not conditions:
            return None
        statement = (
            select(WorkspaceComponent)
            .where(WorkspaceComponent.workspace_id == workspace_id)
            .where(WorkspaceComponent.deleted_at.is_(None))
            .where(WorkspaceComponent.status == RecordStatus.ACTIVE.value)
            .where(WorkspaceComponent.current_version_no > 0)
            .where(or_(*conditions))
            .order_by(WorkspaceComponent.updated_at.desc(), WorkspaceComponent.id.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def _get_project_or_raise(self, project_id: int, *, workspace_id: int | None = None) -> Project:
        """读取项目并按需校验工作空间归属。"""

        project = await self.project_repository.get_by_id(project_id)
        if project is None or (workspace_id is not None and project.workspace_id != workspace_id):
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        return project

    async def _get_style_or_raise(self, workspace_id: int, style_id: int) -> WorkspaceStyle:
        """读取样式并校验工作空间归属。"""

        style = await self.style_repository.get_by_id(workspace_id, style_id)
        if style is None:
            raise AppException(status_code=404, code="WORKSPACE_STYLE_NOT_FOUND", detail="样式不存在。")
        return style

    async def _delete_style_links(self, style_id: int) -> None:
        """删除样式既有建议组件关联。"""

        await self.session.execute(
            delete(WorkspaceStyleSuggestedComponent).where(WorkspaceStyleSuggestedComponent.style_id == style_id)
        )

    async def _delete_project_links(self, project_id: int) -> None:
        """删除项目既有建议组件快照。"""

        await self.session.execute(
            delete(ProjectSuggestedComponent).where(ProjectSuggestedComponent.project_id == project_id)
        )

    @staticmethod
    def _normalize_component_ids(component_ids: list[int]) -> list[int]:
        """规范化组件 ID 列表，去重并保留用户选择顺序。"""

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for value in component_ids:
            component_id = int(value)
            if component_id in seen_ids:
                continue
            seen_ids.add(component_id)
            normalized_ids.append(component_id)
        return normalized_ids

    @staticmethod
    def dump_component_item(component: WorkspaceComponent) -> SuggestedComponentItem:
        """转换组件为不会暴露源码的建议组件摘要。"""

        return SuggestedComponentItem.model_validate(
            {
                "id": component.id,
                "code": component.code,
                "name": component.name,
                "import_name": component.import_name,
                "component_type": WorkspaceComponentType(component.component_type),
                "summary": component.summary,
                "current_version_no": component.current_version_no,
                "available": True,
                "unavailable_reason": None,
            }
        )

    @classmethod
    def dump_component_item_for_management(
        cls,
        component: WorkspaceComponent,
        workspace_id: int,
    ) -> SuggestedComponentItem:
        """转换管理界面摘要，保留不可用组件并提示清理。"""

        unavailable_reason = cls.resolve_unavailable_reason(component, workspace_id)
        item = cls.dump_component_item(component)
        item.available = unavailable_reason is None
        item.unavailable_reason = unavailable_reason
        return item

    @staticmethod
    def resolve_unavailable_reason(component: WorkspaceComponent, workspace_id: int) -> str | None:
        """判断建议组件是否仍可用，并返回面向用户的清理提示。"""

        if component.workspace_id != workspace_id:
            return "组件不属于当前工作空间，请移除后保存。"
        if component.deleted_at is not None:
            return "组件已删除，请移除后保存。"
        if component.status != RecordStatus.ACTIVE.value:
            return "组件已归档，请移除后保存。"
        if component.current_version_no <= 0:
            return "组件未发布，请移除后保存。"
        return None
