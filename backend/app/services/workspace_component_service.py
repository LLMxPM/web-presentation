"""文件功能：封装工作空间组件草稿 CRUD、发布版本读取与当前依赖索引查询逻辑。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.component_preview_schema import validate_component_preview_schema_text
from app.core.code_generator import create_with_generated_code
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import utc_now
from app.models.enums import PageFileType, RecordStatus
from app.models.workspace_component import WorkspaceComponent
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.schemas.common import PagedResponse
from app.schemas.component import (
    WorkspaceComponentCreateRequest,
    WorkspaceComponentCurrentDependencies,
    WorkspaceComponentDependencyItem,
    WorkspaceComponentItem,
    WorkspaceComponentListQuery,
    WorkspaceComponentPublishRequest,
    WorkspaceComponentRestoreDraftRequest,
    WorkspaceComponentUpdateRequest,
    WorkspaceComponentVersionContent,
    WorkspaceComponentVersionListItem,
)
from app.services.component_dependency_service import ComponentDependencyService
from app.services.workspace_service import WorkspaceService
from app.services.workspace_component_version_service import WorkspaceComponentVersionService

CODE_PREFIX_COMPONENT = "CMP"


class WorkspaceComponentService:
    """工作空间组件服务，负责草稿保存、正式发布与依赖查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = WorkspaceComponentRepository(session)
        self.version_repository = WorkspaceComponentVersionRepository(session)
        self.version_service = WorkspaceComponentVersionService(session)
        self.dependency_service = ComponentDependencyService(session)
        self.workspace_service = WorkspaceService(session)

    async def list(self, query: WorkspaceComponentListQuery, *, user_id: int | None = None) -> PagedResponse[WorkspaceComponentItem]:
        """分页查询当前用户可访问的工作空间组件。"""

        if user_id is not None and query.workspace_id is not None:
            await self.workspace_service.ensure_access(query.workspace_id, user_id=user_id)
        items, total = await self.repository.list(query, user_id=user_id)
        return PagedResponse[WorkspaceComponentItem](
            items=[await self._to_item(item) for item in items],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, component_id: int, *, user_id: int | None = None) -> WorkspaceComponentItem:
        """读取单个组件详情，并在传入用户时校验访问权。"""

        component = await self._get_component_or_raise(component_id)
        if user_id is not None:
            await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        return await self._to_item(component)

    async def create(self, payload: WorkspaceComponentCreateRequest, operator_id: int) -> WorkspaceComponentItem:
        """创建工作空间组件草稿，不生成正式发布版本。"""

        if payload.file_type != PageFileType.VUE:
            raise AppException(status_code=400, code="COMPONENT_FILE_TYPE_INVALID", detail="当前阶段仅支持 Vue 组件。")
        if not await self.repository.workspace_exists(payload.workspace_id):
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
        await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
        await self._assert_import_name_available(
            workspace_id=payload.workspace_id,
            import_name=payload.import_name,
            status=payload.status,
        )

        preview_schema = validate_component_preview_schema_text(payload.preview_schema)

        async def write_component(code: str) -> WorkspaceComponent:
            """使用指定编码创建组件草稿并校验依赖。"""

            component = WorkspaceComponent(
                workspace_id=payload.workspace_id,
                code=code,
                content=normalize_text_to_lf(payload.content),
                preview_schema=preview_schema,
                current_version_no=0,
                draft_base_version_no=0,
                file_type=payload.file_type.value,
                name=payload.name,
                import_name=payload.import_name,
                component_type=payload.component_type.value,
                summary=payload.summary,
                status=payload.status.value,
                created_by=operator_id,
                updated_by=operator_id,
            )
            await self.repository.create(component)
            await self.version_service.validate_draft_dependencies(
                component=component,
                content=component.content,
                file_type=component.file_type,
            )
            return component

        component = await create_with_generated_code(
            self.session,
            WorkspaceComponent,
            CODE_PREFIX_COMPONENT,
            write_component,
        )
        reloaded = await self.repository.get_by_id(component.id)
        return await self._to_item(reloaded)

    async def update(self, component_id: int, payload: WorkspaceComponentUpdateRequest, operator_id: int) -> WorkspaceComponentItem:
        """更新组件元数据和草稿源码，不生成正式发布版本。"""

        component = await self._get_component_or_raise(component_id)
        await self.workspace_service.ensure_access(component.workspace_id, user_id=operator_id)
        next_workspace_id = payload.workspace_id if payload.workspace_id is not None else component.workspace_id
        next_import_name = payload.import_name if payload.import_name is not None else component.import_name
        next_status = payload.status if payload.status is not None else RecordStatus(component.status)

        if next_workspace_id != component.workspace_id:
            if not await self.repository.workspace_exists(next_workspace_id):
                raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")
            await self.workspace_service.ensure_access(next_workspace_id, user_id=operator_id)
        await self._assert_import_name_available(
            workspace_id=next_workspace_id,
            import_name=next_import_name,
            status=next_status,
            exclude_component_id=component.id,
        )
        component.workspace_id = next_workspace_id

        next_content = normalize_text_to_lf(payload.content) if payload.content is not None else component.content
        next_preview_schema = component.preview_schema
        if "preview_schema" in payload.model_fields_set:
            next_preview_schema = validate_component_preview_schema_text(payload.preview_schema)
        next_file_type = payload.file_type if payload.file_type is not None else PageFileType(component.file_type)
        if next_file_type != PageFileType.VUE:
            raise AppException(status_code=400, code="COMPONENT_FILE_TYPE_INVALID", detail="当前阶段仅支持 Vue 组件。")
        await self.version_service.validate_draft_dependencies(
            component=component,
            content=next_content,
            file_type=next_file_type,
        )
        component.content = next_content
        component.preview_schema = next_preview_schema
        component.file_type = next_file_type.value

        if payload.name is not None:
            component.name = payload.name
        if payload.import_name is not None:
            component.import_name = payload.import_name
        if payload.component_type is not None:
            component.component_type = payload.component_type.value
        if payload.summary is not None:
            component.summary = payload.summary
        if payload.status is not None:
            component.status = payload.status.value

        component.updated_by = operator_id
        await self.session.commit()
        reloaded = await self.repository.get_by_id(component.id)
        return await self._to_item(reloaded)

    async def publish(self, component_id: int, payload: WorkspaceComponentPublishRequest, operator_id: int) -> WorkspaceComponentItem:
        """发布组件当前草稿，生成可被外部引用的正式版本。"""

        component = await self._get_component_or_raise(component_id)
        await self.workspace_service.ensure_access(component.workspace_id, user_id=operator_id)
        await self.version_service.publish_draft(
            component=component,
            operator_id=operator_id,
            release_name=payload.release_name,
            change_note=payload.change_note,
        )
        component.updated_by = operator_id
        await self.session.commit()
        reloaded = await self.repository.get_by_id(component.id)
        return await self._to_item(reloaded)

    async def list_versions(
        self,
        component_id: int,
        *,
        user_id: int | None = None,
    ) -> list[WorkspaceComponentVersionListItem]:
        """查询组件完整版本历史，传入用户时校验工作空间访问权。"""

        component = await self._get_component_or_raise(component_id)
        if user_id is not None:
            await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        return await self.version_service.list_versions(component)

    async def get_version_content(
        self,
        component_id: int,
        version_no: int,
        *,
        user_id: int | None = None,
    ) -> WorkspaceComponentVersionContent:
        """读取指定组件正式发布版本的完整源码，传入用户时校验访问权。"""

        component = await self._get_component_or_raise(component_id)
        if user_id is not None:
            await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        return await self.version_service.get_version_content(component, version_no)

    async def restore_version_to_draft(
        self,
        component_id: int,
        version_no: int,
        payload: WorkspaceComponentRestoreDraftRequest,
        operator_id: int,
    ) -> WorkspaceComponentItem:
        """将正式发布版本恢复到草稿区，不生成新的发布版本。"""

        component = await self._get_component_or_raise(component_id)
        await self.workspace_service.ensure_access(component.workspace_id, user_id=operator_id)
        await self.version_service.restore_version_to_draft(
            component=component,
            version_no=version_no,
        )
        component.updated_by = operator_id
        await self.session.commit()
        reloaded = await self.repository.get_by_id(component.id)
        return await self._to_item(reloaded)

    async def get_current_dependencies(self, component_id: int, *, user_id: int | None = None) -> WorkspaceComponentCurrentDependencies:
        """读取组件最新已发布版本的源码依赖索引。"""

        component = await self._get_component_or_raise(component_id)
        if user_id is not None:
            await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        component_version = await self.version_repository.get_by_component_and_version(component.id, component.current_version_no)
        if component_version is None:
            return WorkspaceComponentCurrentDependencies(
                component_id=component.id,
                current_version_no=component.current_version_no,
                component_version_id=None,
                dependencies=[],
            )

        dependencies = await self.dependency_service.get_component_dependencies(component_version.id)
        return WorkspaceComponentCurrentDependencies(
            component_id=component.id,
            current_version_no=component.current_version_no,
            component_version_id=component_version.id,
            dependencies=[WorkspaceComponentDependencyItem.model_validate(item) for item in dependencies],
        )

    async def delete(self, component_id: int, *, user_id: int) -> None:
        """对当前用户可访问的工作空间组件执行软删除。"""

        component = await self._get_component_or_raise(component_id)
        await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        component.deleted_at = utc_now()
        await self.session.commit()

    async def get_by_code(self, *, workspace_id: int, component_code: str) -> WorkspaceComponentItem:
        """按工作空间和组件编码读取单个组件详情。"""

        component = await self.repository.get_by_code(component_code)
        if component is None or component.workspace_id != workspace_id:
            raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail="组件不存在。")
        return await self._to_item(component)

    async def _get_component_or_raise(self, component_id: int) -> WorkspaceComponent:
        """读取组件，不存在时抛出标准错误。"""

        component = await self.repository.get_by_id(component_id)
        if component is None:
            raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail="组件不存在。")
        return component

    async def _assert_import_name_available(
        self,
        *,
        workspace_id: int,
        import_name: str,
        status: RecordStatus | str,
        exclude_component_id: int | None = None,
    ) -> None:
        """校验启用组件的源码引用名在同一工作空间内唯一。"""

        normalized_status = status.value if isinstance(status, RecordStatus) else str(status)
        if normalized_status != RecordStatus.ACTIVE.value:
            return

        existing = await self.repository.get_active_by_import_name(
            workspace_id=workspace_id,
            import_name=import_name,
            exclude_component_id=exclude_component_id,
        )
        if existing is not None:
            raise AppException(
                status_code=409,
                code="COMPONENT_IMPORT_NAME_CONFLICT",
                detail=f"组件引用名 {import_name} 已被当前工作空间中的启用组件使用。",
            )

    async def _to_item(self, component: WorkspaceComponent) -> WorkspaceComponentItem:
        """将 ORM 组件对象转换为接口响应结构，并补齐草稿发布状态。"""

        latest_version = None
        if component.current_version_no > 0:
            latest_version = await self.version_repository.get_by_component_and_version(
                component.id,
                component.current_version_no,
            )
        has_unpublished_changes = True
        if latest_version is not None:
            has_unpublished_changes = (
                component.draft_base_version_no != component.current_version_no
                or component.content != latest_version.content
                or component.preview_schema != latest_version.preview_schema
                or component.file_type != latest_version.file_type
            )
        return WorkspaceComponentItem.model_validate(
            {
                "id": component.id,
                "workspace_id": component.workspace_id,
                "workspace_name": getattr(component, "workspace_name", None),
                "code": component.code,
                "content": component.content,
                "preview_schema": component.preview_schema,
                "current_version_no": component.current_version_no,
                "draft_base_version_no": component.draft_base_version_no,
                "published_at": component.published_at,
                "file_type": component.file_type,
                "name": component.name,
                "import_name": component.import_name,
                "component_type": component.component_type,
                "summary": component.summary,
                "status": component.status,
                "created_at": component.created_at,
                "updated_at": component.updated_at,
                "created_by": component.created_by,
                "updated_by": component.updated_by,
                "has_unpublished_changes": has_unpublished_changes,
            }
        )
