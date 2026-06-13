"""文件功能：封装工作空间页面资源库的 CRUD 与访问校验逻辑。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_generator import CODE_PREFIX_PAGE, create_with_generated_code
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import normalize_utc, utc_now
from app.models.enums import PageFileType, ProjectRouteType, RecordStatus
from app.models.page import Page
from app.models.project_route import ProjectRoute
from app.models.workspace import Project
from app.repositories.module_dependency_repository import DEPENDENCY_KIND_PAGE_MODULE
from app.repositories.page_repository import PageRepository
from app.repositories.page_version_repository import PageVersionRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.project_route_repository import ProjectRouteRepository
from app.schemas.common import PagedResponse
from app.schemas.page import (
    PageComponentResourceItem,
    PageCopyToProjectRequest,
    PageCreateRequest,
    PageCurrentComponentIndex,
    PageCurrentModuleDependencies,
    PageModuleDependencyItem,
    PageItem,
    PageListQuery,
    PageSnapshotCreateRequest,
    PageUpdateRequest,
    PageVersionContent,
    PageVersionListItem,
    PageVersionRestoreRequest,
)
from app.services.component_dependency_service import ComponentDependencyService
from app.services.page_version_service import PageVersionService
from app.services.page_component_index_service import PageComponentIndexService
from app.services.project_route_service import ProjectRouteService
from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService
from app.services.project_service import ProjectService
from app.services.workspace_service import WorkspaceService


class PageService:
    """页面服务，负责编码自动生成和软删除。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PageRepository(session)
        self.page_version_repository = PageVersionRepository(session)
        self.project_repository = ProjectRepository(session)
        self.route_repository = ProjectRouteRepository(session)
        self.version_service = PageVersionService(session)
        self.component_index_service = PageComponentIndexService(session)
        self.dependency_service = ComponentDependencyService(session)
        self.screenshot_fingerprint_service = PageScreenshotFingerprintService(session)
        self.project_service = ProjectService(session)
        self.workspace_service = WorkspaceService(session)
        self.settings = get_settings()

    async def list(self, query: PageListQuery, *, user_id: int) -> PagedResponse[PageItem]:
        """查询当前用户可访问页面资源并返回标准分页结构。"""

        if query.workspace_id is not None:
            await self.workspace_service.ensure_access(query.workspace_id, user_id=user_id)
        if query.project_id is not None:
            project = await self.project_service.get(query.project_id, user_id=user_id)
            if query.workspace_id is not None and project.workspace_id != query.workspace_id:
                raise AppException(status_code=403, code="PAGE_SCOPE_DENIED", detail="项目不属于传入的工作空间。")
        items, total = await self.repository.list(query, user_id=user_id)
        route_bindings_map: dict[int, list] = {}
        if query.project_id is not None:
            route_bindings_map = await ProjectRouteService(self.session).build_page_bindings_map(query.project_id)
        screenshot_config_hash_cache: dict[int, str | None] = {}
        page_items = [
            await self._to_item(
                item,
                route_bindings=route_bindings_map.get(item.id),
                screenshot_config_hash_cache=screenshot_config_hash_cache,
            )
            for item in items
        ]
        return PagedResponse[PageItem](
            items=page_items,
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, page_id: int, *, user_id: int | None = None) -> PageItem:
        """获取单个页面详情，并在传入用户时校验工作空间访问权。"""

        page_model = await self._get_page_or_raise(page_id)
        if user_id is not None:
            await self._ensure_page_access(page_model, user_id=user_id)
        route_bindings = None
        if page_model.project_id is not None:
            route_bindings = (await ProjectRouteService(self.session).build_page_bindings_map(page_model.project_id)).get(page_model.id)
        return await self._to_item(page_model, route_bindings=route_bindings)

    async def create(self, payload: PageCreateRequest, operator_id: int) -> PageItem:
        """创建页面资源，code 由系统自动生成。"""

        normalized_page_content = normalize_text_to_lf(payload.page_content)
        if payload.workspace_id is None:
            raise AppException(status_code=400, code="PAGE_WORKSPACE_REQUIRED", detail="页面必须归属于工作空间。")
        await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
        if payload.project_id is not None:
            project = await self.project_service.get(payload.project_id, user_id=operator_id)
            if project.workspace_id != payload.workspace_id:
                raise AppException(status_code=403, code="PAGE_PROJECT_SCOPE_DENIED", detail="页面项目不属于传入工作空间。")

        async def write_page(code: str) -> Page:
            """使用指定编码创建页面及其初始版本。"""

            page_model = Page(
                code=code,
                page_content=normalized_page_content,
                current_version_no=1,
                file_type=payload.file_type.value,
                title=payload.title,
                summary=payload.summary,
                speaker_notes=self._normalize_optional_text(payload.speaker_notes),
                status=payload.status.value,
                workspace_id=payload.workspace_id,
                project_id=payload.project_id,
                created_by=operator_id,
                updated_by=operator_id,
            )
            await self.repository.create(page_model)
            await self.version_service.initialize_page_version(page_model, operator_id)
            return page_model

        page_model = await create_with_generated_code(
            self.session,
            Page,
            CODE_PREFIX_PAGE,
            write_page,
        )
        await self.session.refresh(page_model)
        return await self._to_item(page_model)

    async def copy_to_project(
        self,
        page_id: int,
        payload: PageCopyToProjectRequest,
        operator_id: int,
    ) -> PageItem:
        """将当前页面复制到同工作空间内的另一个启用项目。"""

        source_page = await self._get_page_or_raise(page_id)
        await self._ensure_page_access(source_page, user_id=operator_id)
        target_project = await self._validate_copy_scope(source_page, payload.target_project_id)
        await self.workspace_service.ensure_access(target_project.workspace_id, user_id=operator_id)
        await self._ensure_copy_source_has_no_page_module_dependencies(source_page)

        normalized_page_content = normalize_text_to_lf(source_page.page_content)
        next_title = payload.title if payload.title is not None else source_page.title
        next_summary = payload.summary if "summary" in payload.model_fields_set else source_page.summary

        async def write_page(code: str) -> Page:
            """使用新编码写入复制页面、初始版本和可选路由节点。"""

            page_model = Page(
                code=code,
                page_content=normalized_page_content,
                current_version_no=1,
                file_type=source_page.file_type,
                title=next_title,
                summary=next_summary,
                speaker_notes=source_page.speaker_notes,
                status=RecordStatus.ACTIVE.value,
                workspace_id=target_project.workspace_id,
                project_id=target_project.id,
                created_by=operator_id,
                updated_by=operator_id,
            )
            await self.repository.create(page_model)
            await self.version_service.initialize_page_version(
                page_model,
                operator_id,
                change_note=f"复制自页面 {source_page.code}",
            )
            await self._append_copy_route_if_requested(
                target_project=target_project,
                page_model=page_model,
                payload=payload,
                operator_id=operator_id,
            )
            return page_model

        page_model = await create_with_generated_code(
            self.session,
            Page,
            CODE_PREFIX_PAGE,
            write_page,
        )
        await self.session.refresh(page_model)
        return await self.get(page_model.id)

    async def update(self, page_id: int, payload: PageUpdateRequest, operator_id: int) -> PageItem:
        """更新页面资源元数据，编码不可修改。"""

        page_model = await self._get_page_or_raise(page_id)
        await self._ensure_page_access(page_model, user_id=operator_id)

        next_page_content = (
            normalize_text_to_lf(payload.page_content)
            if payload.page_content is not None
            else page_model.page_content
        )
        next_file_type = payload.file_type if payload.file_type is not None else PageFileType(page_model.file_type)
        next_speaker_notes = (
            self._normalize_optional_text(payload.speaker_notes)
            if "speaker_notes" in payload.model_fields_set
            else page_model.speaker_notes
        )
        await self.version_service.save_new_version(
            page=page_model,
            page_content=next_page_content,
            file_type=next_file_type,
            operator_id=operator_id,
            speaker_notes=next_speaker_notes,
            change_note=payload.change_note,
        )
        if payload.title is not None:
            page_model.title = payload.title
        if payload.summary is not None:
            page_model.summary = payload.summary
        if "speaker_notes" in payload.model_fields_set:
            page_model.speaker_notes = next_speaker_notes
        if payload.status is not None:
            should_remove_route_bindings = (
                payload.status == RecordStatus.ARCHIVED
                and page_model.status != RecordStatus.ARCHIVED.value
                and page_model.project_id is not None
            )
            if should_remove_route_bindings:
                await ProjectRouteService(self.session).remove_page_bindings(page_model.project_id, page_model.id)
            page_model.status = payload.status.value
        if payload.workspace_id is not None:
            await self.workspace_service.ensure_access(payload.workspace_id, user_id=operator_id)
            page_model.workspace_id = payload.workspace_id
        if payload.project_id is not None:
            project = await self.project_service.get(payload.project_id, user_id=operator_id)
            if page_model.workspace_id is not None and project.workspace_id != page_model.workspace_id:
                raise AppException(status_code=403, code="PAGE_PROJECT_SCOPE_DENIED", detail="页面项目不属于传入工作空间。")
            page_model.project_id = payload.project_id

        page_model.updated_by = operator_id
        await self.session.commit()
        await self.session.refresh(page_model)
        return await self._to_item(page_model)

    async def list_versions(self, page_id: int, *, user_id: int | None = None) -> list[PageVersionListItem]:
        """返回页面的完整版本历史，最新版本排在最前。"""

        page_model = await self._get_page_or_raise(page_id)
        if user_id is not None:
            await self._ensure_page_access(page_model, user_id=user_id)
        return await self.version_service.list_versions(page_model)

    async def get_version_content(self, page_id: int, version_no: int, *, user_id: int | None = None) -> PageVersionContent:
        """读取指定页面版本的完整源码内容。"""

        page_model = await self._get_page_or_raise(page_id)
        if user_id is not None:
            await self._ensure_page_access(page_model, user_id=user_id)
        return await self.version_service.get_version_content(page_model, version_no)

    async def create_snapshot(
        self,
        page_id: int,
        version_no: int,
        payload: PageSnapshotCreateRequest,
    ) -> PageVersionContent:
        """将指定版本标记为重点快照。"""

        page_model = await self._get_page_or_raise(page_id)
        snapshot = await self.version_service.create_snapshot(page_model, version_no, payload.snapshot_name)
        await self.session.commit()
        return snapshot

    async def restore_version(
        self,
        page_id: int,
        version_no: int,
        payload: PageVersionRestoreRequest,
        operator_id: int,
    ) -> PageItem:
        """恢复历史版本为最新版本，并返回最新页面详情。"""

        page_model = await self._get_page_or_raise(page_id)
        await self._ensure_page_access(page_model, user_id=operator_id)
        await self.version_service.restore_version(page_model, version_no, operator_id, payload.change_note)
        page_model.updated_by = operator_id
        await self.session.commit()
        await self.session.refresh(page_model)
        return await self._to_item(page_model)

    async def delete(self, page_id: int, *, user_id: int) -> None:
        """对当前用户可访问页面资源执行软删除。"""

        page_model = await self._get_page_or_raise(page_id)
        await self._ensure_page_access(page_model, user_id=user_id)
        page_model.deleted_at = utc_now()
        await self.session.commit()

    async def get_current_component_index(self, page_id: int, *, user_id: int | None = None) -> PageCurrentComponentIndex:
        """读取页面当前版本的组件索引信息，供详情页快速展示。"""

        page_model = await self._get_page_or_raise(page_id)
        if user_id is not None:
            await self._ensure_page_access(page_model, user_id=user_id)
        page_version = await self.page_version_repository.get_by_page_and_version(page_model.id, page_model.current_version_no)
        if page_version is None:
            return PageCurrentComponentIndex(
                page_id=page_model.id,
                current_version_no=page_model.current_version_no,
                page_version_id=None,
                components=[],
                resources=[],
            )

        component_names = await self.component_index_service.list_component_names_by_version(page_version.id)
        resource_items = await self.component_index_service.list_resource_items_by_version(page_version.id)
        return PageCurrentComponentIndex(
            page_id=page_model.id,
            current_version_no=page_model.current_version_no,
            page_version_id=page_version.id,
            components=component_names,
            resources=[
                PageComponentResourceItem(
                    component_name=item.component_name,
                    resource_attr=item.resource_attr,
                    resource_name=item.resource_name,
                )
                for item in resource_items
            ],
        )

    async def get_current_module_dependencies(self, page_id: int, *, user_id: int | None = None) -> PageCurrentModuleDependencies:
        """读取页面当前版本的源码依赖索引。"""

        page_model = await self._get_page_or_raise(page_id)
        if user_id is not None:
            await self._ensure_page_access(page_model, user_id=user_id)
        page_version = await self.page_version_repository.get_by_page_and_version(page_model.id, page_model.current_version_no)
        if page_version is None:
            return PageCurrentModuleDependencies(
                page_id=page_model.id,
                current_version_no=page_model.current_version_no,
                page_version_id=None,
                dependencies=[],
            )

        dependency_items = await self.dependency_service.get_page_dependencies(page_version.id)
        return PageCurrentModuleDependencies(
            page_id=page_model.id,
            current_version_no=page_model.current_version_no,
            page_version_id=page_version.id,
            dependencies=[PageModuleDependencyItem.model_validate(item) for item in dependency_items],
        )

    async def _get_page_or_raise(self, page_id: int) -> Page:
        """读取页面，不存在时统一抛出标准错误。"""

        page_model = await self.repository.get_by_id(page_id)
        if page_model is None:
            raise AppException(status_code=404, code="PAGE_NOT_FOUND", detail="页面不存在。")
        return page_model

    async def _ensure_page_access(self, page_model: Page, *, user_id: int) -> None:
        """校验页面所属工作空间对当前用户可见。"""

        if page_model.workspace_id is None:
            raise AppException(status_code=403, code="PAGE_ACCESS_DENIED", detail="页面未归属工作空间，无法访问。")
        await self.workspace_service.ensure_access(page_model.workspace_id, user_id=user_id)

    async def _validate_copy_scope(self, source_page: Page, target_project_id: int) -> Project:
        """校验页面复制的项目范围，确保 v1 只在同工作空间内跨项目复制。"""

        if source_page.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=400, code="PAGE_COPY_SOURCE_INACTIVE", detail="源页面不是启用状态，不能复制。")
        if source_page.workspace_id is None or source_page.project_id is None:
            raise AppException(status_code=400, code="PAGE_COPY_SOURCE_UNBOUND", detail="源页面未关联工作空间或项目，不能复制。")
        if source_page.project_id == target_project_id:
            raise AppException(status_code=400, code="PAGE_COPY_TARGET_SAME_PROJECT", detail="不能将页面复制到源项目自身。")

        target_project = await self.project_repository.get_by_id(target_project_id)
        if target_project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="目标项目不存在。")
        if target_project.status != RecordStatus.ACTIVE.value:
            raise AppException(status_code=400, code="PAGE_COPY_TARGET_PROJECT_INACTIVE", detail="目标项目不是启用状态，不能复制页面。")
        if target_project.workspace_id != source_page.workspace_id:
            raise AppException(status_code=400, code="PAGE_COPY_WORKSPACE_MISMATCH", detail="v1 仅支持同一工作空间内复制页面。")
        return target_project

    async def _ensure_copy_source_has_no_page_module_dependencies(self, source_page: Page) -> None:
        """阻断引用其他页面模块的源码，避免复制后目标项目缺少依赖页面。"""

        page_version = await self.page_version_repository.get_by_page_and_version(
            source_page.id,
            source_page.current_version_no,
        )
        if page_version is not None:
            dependencies = await self.dependency_service.get_page_dependencies(page_version.id)
            has_page_module_dependency = any(
                item["dependency_kind"] == DEPENDENCY_KIND_PAGE_MODULE
                for item in dependencies
            )
            if has_page_module_dependency:
                raise AppException(
                    status_code=400,
                    code="PAGE_COPY_PAGE_MODULE_DEPENDENCY_UNSUPPORTED",
                    detail="源页面引用了其他页面模块，v1 暂不支持单页跨项目复制这类依赖。",
                )
            return

        if source_page.file_type != PageFileType.VUE.value:
            return

        parsed = self.dependency_service.parse_dependencies(
            source_page.page_content,
            source_label=f"页面 {source_page.code}",
            importer_module_path=f"src/views/{source_page.code}.{source_page.file_type}",
            allow_page_module_imports=True,
        )
        if parsed.page_module_imports:
            raise AppException(
                status_code=400,
                code="PAGE_COPY_PAGE_MODULE_DEPENDENCY_UNSUPPORTED",
                detail="源页面引用了其他页面模块，v1 暂不支持单页跨项目复制这类依赖。",
            )

    async def _append_copy_route_if_requested(
        self,
        *,
        target_project: Project,
        page_model: Page,
        payload: PageCopyToProjectRequest,
        operator_id: int,
    ) -> None:
        """按复制入参追加顶层或分组页面路由，由外层事务统一提交。"""

        if payload.route_placement == "none":
            return
        if page_model.file_type != PageFileType.VUE.value:
            raise AppException(
                status_code=400,
                code="PROJECT_ROUTE_PAGE_TYPE_INVALID",
                detail=f"页面 {page_model.id}（{page_model.code}）不是 Vue 页面，不能作为项目路由页面。",
            )

        routes = await self.route_repository.list_by_project(target_project.id)
        parent_id: int | None = None
        if payload.route_placement == "group":
            if payload.parent_route_id is None:
                raise AppException(status_code=400, code="PAGE_COPY_ROUTE_GROUP_REQUIRED", detail="复制到分组路由时必须指定目标分组。")
            parent_route = next((route for route in routes if route.id == payload.parent_route_id), None)
            if (
                parent_route is None
                or parent_route.project_id != target_project.id
                or parent_route.route_type != ProjectRouteType.GROUP.value
            ):
                raise AppException(status_code=400, code="PAGE_COPY_ROUTE_GROUP_INVALID", detail="目标路由分组不存在或不属于目标项目。")
            parent_id = parent_route.id
        elif payload.route_placement != "root":
            raise AppException(status_code=400, code="PAGE_COPY_ROUTE_PLACEMENT_INVALID", detail="复制页面路由位置不合法。")

        siblings = [route for route in routes if route.parent_id == parent_id]
        route_base = str(payload.route or page_model.code.lower()).strip()
        ProjectRouteService._ensure_valid_route_segment(route_base, source_label="复制页面路由")
        route_segment = self._build_unique_copy_route_segment(route_base, siblings)
        order = max((route.order for route in siblings), default=0) + 10

        await self.route_repository.create(
            ProjectRoute(
                project_id=target_project.id,
                parent_id=parent_id,
                route=route_segment,
                order=order,
                hidden=False,
                page_id=page_model.id,
                route_type=ProjectRouteType.PAGE.value,
                group_title=None,
                created_by=operator_id,
                updated_by=operator_id,
            )
        )

    @staticmethod
    def _build_unique_copy_route_segment(route_base: str, siblings: list[ProjectRoute]) -> str:
        """在同级路由中为复制页生成不冲突的路由片段。"""

        existing_routes = {route.route for route in siblings}
        if route_base not in existing_routes:
            return route_base

        index = 2
        while True:
            candidate = f"{route_base}-{index}"
            if candidate not in existing_routes:
                return candidate
            index += 1

    async def _to_item(
        self,
        page_model: Page,
        *,
        route_bindings: list | None = None,
        screenshot_config_hash_cache: dict[int, str | None] | None = None,
    ) -> PageItem:
        """统一补齐页面截图公开地址后再输出响应。"""

        resolved_route_bindings = route_bindings if route_bindings is not None else []
        screenshot_url = self._build_versioned_screenshot_url(page_model)
        screenshot_is_latest = await self._is_page_screenshot_latest(
            page_model,
            screenshot_url=screenshot_url,
            screenshot_config_hash_cache=screenshot_config_hash_cache,
        )
        return PageItem.model_validate(
            {
                **PageItem.model_validate(page_model).model_dump(),
                "screenshot_url": screenshot_url,
                "screenshot_version_no": page_model.screenshot_version_no,
                "screenshot_config_hash": page_model.screenshot_config_hash,
                "screenshot_is_latest": screenshot_is_latest,
                "screenshot_updated_at": page_model.screenshot_updated_at,
                "is_in_project_route": None if page_model.project_id is None else bool(resolved_route_bindings),
                "route_bindings": resolved_route_bindings,
            }
        )

    async def _is_page_screenshot_latest(
        self,
        page_model: Page,
        *,
        screenshot_url: str | None,
        screenshot_config_hash_cache: dict[int, str | None] | None = None,
    ) -> bool:
        """判断页面截图是否同时匹配当前页面版本和项目展示配置。"""

        if (
            screenshot_url is None
            or page_model.screenshot_version_no is None
            or page_model.screenshot_version_no != page_model.current_version_no
            or not page_model.screenshot_config_hash
        ):
            return False

        current_config_hash = await self._resolve_page_screenshot_config_hash(
            page_model,
            screenshot_config_hash_cache=screenshot_config_hash_cache,
        )
        return current_config_hash is not None and page_model.screenshot_config_hash == current_config_hash

    async def _resolve_page_screenshot_config_hash(
        self,
        page_model: Page,
        *,
        screenshot_config_hash_cache: dict[int, str | None] | None = None,
    ) -> str | None:
        """解析当前截图配置指纹；配置异常时让列表保守标记为旧截图。"""

        cache_key = int(page_model.project_id or 0)
        if screenshot_config_hash_cache is not None and cache_key in screenshot_config_hash_cache:
            return screenshot_config_hash_cache[cache_key]

        try:
            config_hash = (await self.screenshot_fingerprint_service.build_page_snapshot(page_model)).config_hash
        except AppException:
            config_hash = None

        if screenshot_config_hash_cache is not None:
            screenshot_config_hash_cache[cache_key] = config_hash
        return config_hash

    def _build_versioned_screenshot_url(self, page_model: Page) -> str | None:
        """生成截图公开地址，并用截图更新时间作为浏览器缓存刷新版本。"""

        if page_model.screenshot_storage_key is None:
            return None

        screenshot_url = (
            f"{self.settings.backend_public_base_url.rstrip('/')}"
            f"/public/page-screenshots/{page_model.id}"
        )
        if page_model.screenshot_updated_at is None:
            return screenshot_url

        version = int(normalize_utc(page_model.screenshot_updated_at).timestamp() * 1000)
        separator = "&" if "?" in screenshot_url else "?"
        return f"{screenshot_url}{separator}v={version}"

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """归一化可空长文本字段；空白字符串保留为空字符串，便于明确清空。"""

        return normalize_text_to_lf(value) if value is not None else None
