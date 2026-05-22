"""文件功能：封装工作空间组件草稿发布、发布版本读取与依赖索引维护。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import format_in_app_timezone, utc_now
from app.models.enums import PageFileType
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.schemas.component import WorkspaceComponentVersionContent, WorkspaceComponentVersionListItem
from app.services.component_dependency_service import ComponentDependencyService
from app.services.component_resource_index_service import ComponentResourceIndexService


class WorkspaceComponentVersionService:
    """工作空间组件发布版本服务，负责从草稿生成不可变版本并维护依赖索引。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = WorkspaceComponentVersionRepository(session)
        self.dependency_service = ComponentDependencyService(session)
        self.resource_index_service = ComponentResourceIndexService(session)

    @staticmethod
    def _build_timestamp_label(dt: datetime | None = None) -> str:
        """生成组件版本展示版号，时间基于业务时区。"""

        return format_in_app_timezone(dt, "%Y%m%d-%H%M%S")

    async def validate_draft_dependencies(
        self,
        *,
        component: WorkspaceComponent,
        content: str,
        file_type: PageFileType | str,
    ) -> None:
        """校验组件草稿依赖是否合法，但不生成正式发布索引。"""

        normalized_file_type = file_type.value if isinstance(file_type, PageFileType) else str(file_type)
        if normalized_file_type != PageFileType.VUE.value:
            raise AppException(status_code=400, code="COMPONENT_FILE_TYPE_INVALID", detail="当前阶段仅支持 Vue 组件。")

        parsed = self.dependency_service.parse_dependencies(
            normalize_text_to_lf(content),
            source_label=f"组件 {component.code}",
            importer_module_path=f"src/workspace-components/{component.code}/draft.vue",
        )
        component_dependencies = await self.dependency_service.resolve_component_dependencies(
            workspace_id=component.workspace_id,
            component_refs=parsed.component_imports,
            source_label=f"组件 {component.code}",
        )
        root_version = await self.repository.get_by_component_and_version(
            component.id,
            component.current_version_no,
        ) if component.current_version_no > 0 else None
        await self.dependency_service.assert_transient_component_dependencies_have_no_cycle(
            root_component_version_id=root_version.id if root_version is not None else None,
            dependency_version_ids=[item.component_version_id for item in component_dependencies],
        )

    async def publish_draft(
        self,
        *,
        component: WorkspaceComponent,
        operator_id: int,
        release_name: str | None = None,
        change_note: str | None = None,
    ) -> WorkspaceComponentVersion | None:
        """将组件当前草稿发布为新的不可变版本。"""

        normalized_content = normalize_text_to_lf(component.content)
        component.content = normalized_content
        normalized_file_type = str(component.file_type)
        await self.validate_draft_dependencies(
            component=component,
            content=normalized_content,
            file_type=normalized_file_type,
        )

        created_at = utc_now()
        version = WorkspaceComponentVersion(
            component_id=component.id,
            version_no=component.current_version_no + 1,
            version_label=self._build_timestamp_label(created_at),
            release_name=release_name,
            file_type=normalized_file_type,
            content=normalized_content,
            preview_schema=component.preview_schema,
            change_note=change_note,
            created_by=operator_id,
            created_at=created_at,
            updated_at=created_at,
        )
        await self.repository.create(version)
        await self.dependency_service.rebuild_component_version_dependencies(
            component=component,
            component_version=version,
            content=normalized_content,
            file_type=normalized_file_type,
        )
        await self.resource_index_service.rebuild_component_version_index(
            component=component,
            component_version=version,
        )

        component.current_version_no = version.version_no
        component.draft_base_version_no = version.version_no
        component.published_at = created_at
        return version

    async def list_versions(self, component: WorkspaceComponent) -> list[WorkspaceComponentVersionListItem]:
        """列出组件的正式发布版本历史。"""

        versions = await self.repository.list_by_component_id(component.id, descending=True)
        return [
            WorkspaceComponentVersionListItem(
                id=version.id,
                component_id=version.component_id,
                version_no=version.version_no,
                version_label=version.version_label,
                release_name=version.release_name,
                file_type=version.file_type,
                is_current=version.version_no == component.current_version_no,
                content_size=len(version.content),
                change_note=version.change_note,
                created_at=version.created_at,
                created_by=version.created_by,
            )
            for version in versions
        ]

    async def get_version_content(self, component: WorkspaceComponent, version_no: int) -> WorkspaceComponentVersionContent:
        """读取指定组件发布版本的完整源码。"""

        version = await self.repository.get_by_component_and_version(component.id, version_no)
        if version is None:
            raise AppException(status_code=404, code="COMPONENT_VERSION_NOT_FOUND", detail="组件版本不存在。")

        return WorkspaceComponentVersionContent(
            component_id=component.id,
            version_no=version.version_no,
            version_label=version.version_label,
            release_name=version.release_name,
            file_type=version.file_type,
            is_current=version.version_no == component.current_version_no,
            content=version.content,
            preview_schema=version.preview_schema,
            change_note=version.change_note,
            created_at=version.created_at,
            created_by=version.created_by,
        )

    async def restore_version_to_draft(
        self,
        *,
        component: WorkspaceComponent,
        version_no: int,
    ) -> WorkspaceComponentVersion:
        """将指定发布版本恢复到组件草稿区，不生成新发布版本。"""

        version = await self.repository.get_by_component_and_version(component.id, version_no)
        if version is None:
            raise AppException(status_code=404, code="COMPONENT_VERSION_NOT_FOUND", detail="组件版本不存在。")

        component.content = normalize_text_to_lf(version.content)
        component.preview_schema = version.preview_schema
        component.file_type = version.file_type
        component.draft_base_version_no = version.version_no
        return version
