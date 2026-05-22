"""文件功能：提供项目路由树的校验、持久化、页面绑定摘要与 Runtime 转换能力。"""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, PageFileType, ProjectRouteType, RecordStatus
from app.models.page import Page
from app.models.project_route import ProjectRoute
from app.models.workspace import Project
from app.repositories.page_repository import PageRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.project_route_repository import ProjectRouteRepository
from app.schemas.project_route import (
    ProjectRouteChildItem,
    ProjectRouteChildWrite,
    ProjectRouteItemWrite,
    ProjectRoutePageBinding,
    ProjectRouteTreeItem,
    ProjectRouteTreeResponse,
    ProjectRouteTreeWriteRequest,
)


class ProjectRouteService:
    """项目路由服务，负责结构化路由树的读取、覆盖保存与运行时转换。"""

    ROUTE_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_repository = ProjectRepository(session)
        self.page_repository = PageRepository(session)
        self.route_repository = ProjectRouteRepository(session)

    async def get_tree(self, project_id: int) -> ProjectRouteTreeResponse:
        """读取项目路由树，并补齐页面展示字段。"""

        project = await self._get_project_or_raise(project_id)
        routes = await self.route_repository.list_by_project(project.id)
        return await self._build_tree_response(routes)

    async def replace_tree(
        self,
        project_id: int,
        payload: ProjectRouteTreeWriteRequest,
        operator_id: int,
    ) -> ProjectRouteTreeResponse:
        """按整树覆盖方式保存项目路由配置。"""

        project = await self._get_project_or_raise(project_id)
        page_map = await self._validate_write_payload(project, payload)

        await self.route_repository.delete_by_project(project.id)
        for route_item in payload.routes:
            if route_item.route_type == ProjectRouteType.GROUP.value:
                root = await self.route_repository.create(
                    ProjectRoute(
                        project_id=project.id,
                        parent_id=None,
                        route=route_item.route.strip(),
                        order=route_item.order,
                        icon=self._normalize_optional_icon(route_item.icon),
                        hidden=route_item.hidden,
                        page_id=None,
                        route_type=ProjectRouteType.GROUP.value,
                        group_title=str(route_item.group_title or "").strip(),
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )
                for child in route_item.children:
                    await self._create_page_route_node(
                        project_id=project.id,
                        parent_id=root.id,
                        route_item=child,
                        operator_id=operator_id,
                    )
                continue

            await self._create_page_route_node(
                project_id=project.id,
                parent_id=None,
                route_item=route_item,
                operator_id=operator_id,
            )

        await self.session.commit()
        routes = await self.route_repository.list_by_project(project.id)
        return await self._build_tree_response(routes, page_map=page_map)

    async def validate_tree_payload(
        self,
        project_id: int,
        payload: ProjectRouteTreeWriteRequest,
    ) -> dict[int, Page]:
        """校验拟写入路由树，不执行数据库修改。"""

        project = await self._get_project_or_raise(project_id)
        return await self._validate_write_payload(project, payload)

    async def remove_route_node(
        self,
        project_id: int,
        route_id: int,
        operator_id: int,
    ) -> ProjectRouteTreeResponse:
        """移除指定路由节点；若目标是分组，会连同子路由一起移除。"""

        tree = await self.get_tree(project_id)
        found = False
        next_routes: list[ProjectRouteItemWrite] = []
        for item in tree.routes:
            if item.id == route_id:
                found = True
                continue
            if item.route_type == ProjectRouteType.GROUP.value:
                children: list[ProjectRouteChildWrite] = []
                for child in item.children:
                    if child.id == route_id:
                        found = True
                        continue
                    children.append(
                        ProjectRouteChildWrite(
                            route=child.route,
                            order=child.order,
                            icon=child.icon,
                            hidden=child.hidden,
                            page_id=child.page_id,
                        )
                    )
                if not children:
                    continue
                next_routes.append(
                    ProjectRouteItemWrite(
                        route_type=ProjectRouteType.GROUP.value,
                        route=item.route,
                        order=item.order,
                        icon=item.icon,
                        hidden=item.hidden,
                        group_title=item.group_title,
                        children=children,
                    )
                )
                continue
            next_routes.append(
                ProjectRouteItemWrite(
                    route_type=ProjectRouteType.PAGE.value,
                    route=item.route,
                    order=item.order,
                    icon=item.icon,
                    hidden=item.hidden,
                    page_id=item.page_id,
                )
            )

        if not found:
            raise AppException(status_code=404, code="PROJECT_ROUTE_NODE_NOT_FOUND", detail="路由节点不存在。")
        return await self.replace_tree(
            project_id,
            ProjectRouteTreeWriteRequest(routes=next_routes),
            operator_id,
        )

    async def remove_page_bindings(self, project_id: int, page_id: int) -> None:
        """移除页面在项目路由中的所有绑定，并由调用方统一提交事务。"""

        project = await self._get_project_or_raise(project_id)
        await self.route_repository.delete_page_bindings(project.id, page_id)
        routes = await self.route_repository.list_by_project(project.id)
        children_by_parent = self._group_children(routes)
        empty_group_ids = [
            route.id
            for route in routes
            if route.route_type == ProjectRouteType.GROUP.value and not children_by_parent.get(route.id)
        ]
        await self.route_repository.delete_by_ids(empty_group_ids)

    async def build_runtime_route_config(self, project_id: int) -> dict[str, list[dict[str, object]]]:
        """生成 Runtime 可直接消费的项目路由结构。"""

        project = await self._get_project_or_raise(project_id)
        routes = await self.route_repository.list_by_project(project.id)
        page_map = await self._load_pages_for_routes(routes)
        self._ensure_pages_are_runtime_ready(project, page_map)
        children_by_parent = self._group_children(routes)

        runtime_routes: list[dict[str, object]] = []
        for route in self._sort_routes(children_by_parent.get(None, [])):
            if route.route_type == ProjectRouteType.GROUP.value:
                runtime_routes.append(
                    {
                        "route": route.route,
                        "meta": self._build_runtime_meta(
                            title=str(route.group_title or "").strip(),
                            order=route.order,
                            icon=route.icon,
                            hidden=route.hidden,
                        ),
                        "children": [
                            self._build_runtime_page_route(child, page_map[child.page_id])
                            for child in self._sort_routes(children_by_parent.get(route.id, []))
                        ],
                    }
                )
                continue

            runtime_routes.append(self._build_runtime_page_route(route, page_map[route.page_id]))

        return {"routes": runtime_routes}

    async def build_page_bindings_map(
        self,
        project_id: int,
    ) -> dict[int, list[ProjectRoutePageBinding]]:
        """构建项目页面到路由路径的引用摘要。"""

        project = await self._get_project_or_raise(project_id)
        routes = await self.route_repository.list_by_project(project.id)
        bindings: dict[int, list[ProjectRoutePageBinding]] = defaultdict(list)
        route_map = {route.id: route for route in routes}

        for route in self._sort_routes(routes):
            if route.page_id is None:
                continue
            parent = route_map.get(route.parent_id) if route.parent_id else None
            parent_route = parent.route if parent is not None else None
            bindings[route.page_id].append(
                ProjectRoutePageBinding(
                    route_id=route.id,
                    parent_route=parent_route,
                    route=route.route,
                    full_path=self._build_full_path(parent_route, route.route),
                    parent_order=parent.order if parent is not None else None,
                    order=route.order,
                )
            )

        return bindings

    async def _build_tree_response(
        self,
        routes: list[ProjectRoute],
        *,
        page_map: dict[int, Page] | None = None,
    ) -> ProjectRouteTreeResponse:
        """将数据库节点转为编辑器使用的两级路由树结构。"""

        resolved_page_map = page_map or await self._load_pages_for_routes(routes)
        children_by_parent = self._group_children(routes)
        response_items: list[ProjectRouteTreeItem] = []

        for route in self._sort_routes(children_by_parent.get(None, [])):
            if route.route_type == ProjectRouteType.GROUP.value:
                response_items.append(
                    ProjectRouteTreeItem(
                        id=route.id,
                        route_type=ProjectRouteType.GROUP.value,
                        route=route.route,
                        order=route.order,
                        icon=route.icon,
                        hidden=route.hidden,
                        group_title=route.group_title,
                        display_title=str(route.group_title or "").strip(),
                        children=[
                            self._build_child_item(child, resolved_page_map[child.page_id])
                            for child in self._sort_routes(children_by_parent.get(route.id, []))
                        ],
                    )
                )
                continue

            page = resolved_page_map[route.page_id]
            response_items.append(
                ProjectRouteTreeItem(
                    id=route.id,
                    route_type=ProjectRouteType.PAGE.value,
                    route=route.route,
                    order=route.order,
                    icon=route.icon,
                    hidden=route.hidden,
                    page_id=page.id,
                    page_code=page.code,
                    page_title=page.title,
                    display_title=page.title,
                )
            )

        return ProjectRouteTreeResponse(routes=response_items)

    async def _create_page_route_node(
        self,
        *,
        project_id: int,
        parent_id: int | None,
        route_item: ProjectRouteItemWrite | ProjectRouteChildWrite,
        operator_id: int,
    ) -> None:
        """创建绑定页面的路由节点。"""

        await self.route_repository.create(
            ProjectRoute(
                project_id=project_id,
                parent_id=parent_id,
                route=route_item.route.strip(),
                order=route_item.order,
                icon=self._normalize_optional_icon(route_item.icon),
                hidden=route_item.hidden,
                page_id=route_item.page_id,
                route_type=ProjectRouteType.PAGE.value,
                group_title=None,
                created_by=operator_id,
                updated_by=operator_id,
            )
        )

    async def _validate_write_payload(
        self,
        project: Project,
        payload: ProjectRouteTreeWriteRequest,
    ) -> dict[int, Page]:
        """校验整树写入请求的路径结构和页面引用合法性。"""

        root_routes: set[str] = set()
        page_ids: list[int] = []
        route_icon_names: list[str] = []

        for route_item in payload.routes:
            normalized_root_route = route_item.route.strip()
            self._ensure_valid_route_segment(normalized_root_route, source_label="顶层路由")
            if normalized_root_route in root_routes:
                raise AppException(status_code=400, code="PROJECT_ROUTE_DUPLICATE_ROUTE", detail=f"顶层路由重复：{normalized_root_route}")
            root_routes.add(normalized_root_route)
            self._append_unique_icon_name(route_icon_names, route_item.icon)

            if route_item.route_type == ProjectRouteType.GROUP.value:
                child_routes: set[str] = set()
                for child in route_item.children:
                    normalized_child_route = child.route.strip()
                    self._ensure_valid_route_segment(
                        normalized_child_route,
                        source_label=f"分组 {normalized_root_route} 下的子路由",
                    )
                    if normalized_child_route in child_routes:
                        raise AppException(
                            status_code=400,
                            code="PROJECT_ROUTE_DUPLICATE_CHILD_ROUTE",
                            detail=f"分组 {normalized_root_route} 下存在重复子路由：{normalized_child_route}",
                        )
                    child_routes.add(normalized_child_route)
                    page_ids.append(child.page_id)
                    self._append_unique_icon_name(route_icon_names, child.icon)
                continue

            if route_item.page_id is not None:
                page_ids.append(route_item.page_id)

        await self._ensure_route_icons_exist(project.workspace_id, route_icon_names)

        page_items = await self.page_repository.list_by_ids(page_ids)
        page_map = {page.id: page for page in page_items}
        missing_page_ids = [page_id for page_id in page_ids if page_id not in page_map]
        if missing_page_ids:
            raise AppException(
                status_code=400,
                code="PROJECT_ROUTE_PAGE_NOT_FOUND",
                detail=f"路由引用的页面不存在：{', '.join(str(page_id) for page_id in missing_page_ids)}。",
            )

        self._ensure_pages_are_runtime_ready(project, page_map)
        return page_map

    async def _ensure_route_icons_exist(self, workspace_id: int, icon_names: list[str]) -> None:
        """校验路由声明的图标名必须对应当前工作空间内启用中的 icon 资源。"""

        if not icon_names:
            return

        rows = await self.session.scalars(
            select(WorkspaceAsset.name)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.asset_type == AssetType.ICON.value)
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
        )
        available_icon_names = {
            normalized_name
            for name in rows.all()
            if (normalized_name := self._normalize_optional_icon(name)) is not None
        }
        missing_icon_names = [name for name in icon_names if name not in available_icon_names]
        if not missing_icon_names:
            return

        raise AppException(
            status_code=400,
            code="PROJECT_ROUTE_ICON_ASSET_NOT_FOUND",
            detail=f"以下路由 Icon 资源在当前工作空间中不存在：{', '.join(missing_icon_names)}。",
        )

    @classmethod
    def _ensure_valid_route_segment(cls, route: str, *, source_label: str) -> None:
        """校验 Runtime 项目路由只能使用单段相对片段。"""

        if cls.ROUTE_SEGMENT_PATTERN.fullmatch(route):
            return
        raise AppException(
            status_code=400,
            code="PROJECT_ROUTE_INVALID_SEGMENT",
            detail=(
                f"{source_label} `{route or '<blank>'}` 不合法。"
                "Runtime 项目路由只支持单段相对片段，例如 home、chapter-1 或 PAGE_01；"
                "不允许 /、/home、home/、a/b、空白或包含空格的路由。"
            ),
        )

    def _ensure_pages_are_runtime_ready(self, project: Project, page_map: dict[int, Page]) -> None:
        """校验路由绑定页面均属于当前项目且可用于 Runtime。"""

        for page in page_map.values():
            if page.project_id != project.id:
                raise AppException(
                    status_code=400,
                    code="PROJECT_ROUTE_PAGE_MISMATCH",
                    detail=f"页面 {page.id}（{page.code}）未关联到当前项目，不能写入项目路由配置。",
                )
            if page.status != RecordStatus.ACTIVE.value:
                raise AppException(
                    status_code=400,
                    code="PROJECT_ROUTE_PAGE_INACTIVE",
                    detail=f"页面 {page.id}（{page.code}）当前不是启用状态，不能写入项目路由配置。",
                )
            if str(page.file_type) != PageFileType.VUE.value:
                raise AppException(
                    status_code=400,
                    code="PROJECT_ROUTE_PAGE_TYPE_INVALID",
                    detail=f"页面 {page.id}（{page.code}）不是 Vue 页面，不能作为项目路由页面。",
                )

    async def _load_pages_for_routes(self, routes: list[ProjectRoute]) -> dict[int, Page]:
        """按路由树中引用的页面主键批量加载页面。"""

        page_ids = [route.page_id for route in routes if route.page_id is not None]
        page_items = await self.page_repository.list_by_ids(page_ids)
        page_map = {page.id: page for page in page_items}
        missing_page_ids = [page_id for page_id in page_ids if page_id not in page_map]
        if missing_page_ids:
            raise AppException(
                status_code=400,
                code="PROJECT_ROUTE_PAGE_NOT_FOUND",
                detail=f"路由引用的页面不存在：{', '.join(str(page_id) for page_id in missing_page_ids)}。",
            )
        return page_map

    async def _get_project_or_raise(self, project_id: int) -> Project:
        """读取项目，不存在时抛出统一错误。"""

        project = await self.project_repository.get_by_id(project_id)
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在。")
        return project

    @staticmethod
    def _group_children(routes: list[ProjectRoute]) -> dict[int | None, list[ProjectRoute]]:
        """按 parent_id 聚合路由节点，方便还原树结构。"""

        grouped: dict[int | None, list[ProjectRoute]] = defaultdict(list)
        for route in routes:
            grouped[route.parent_id].append(route)
        return grouped

    @staticmethod
    def _sort_routes(routes: list[ProjectRoute]) -> list[ProjectRoute]:
        """按 order 和 id 稳定排序节点。"""

        return sorted(routes, key=lambda item: (item.order, item.id))

    @staticmethod
    def _build_child_item(route: ProjectRoute, page: Page) -> ProjectRouteChildItem:
        """将子页面节点转为响应模型。"""

        return ProjectRouteChildItem(
            id=route.id,
            route=route.route,
            order=route.order,
            icon=route.icon,
            hidden=route.hidden,
            page_id=page.id,
            page_code=page.code,
            page_title=page.title,
            display_title=page.title,
        )

    def _build_runtime_page_route(self, route: ProjectRoute, page: Page) -> dict[str, object]:
        """生成 Runtime 使用的页面路由节点。"""

        return {
            "route": route.route,
            "component": f"@/views/{page.code}.{page.file_type}",
            "meta": self._build_runtime_meta(
                title=page.title,
                order=route.order,
                icon=route.icon,
                hidden=route.hidden,
            ),
        }

    @staticmethod
    def _build_runtime_meta(*, title: str, order: int, icon: str | None, hidden: bool) -> dict[str, object]:
        """按 Runtime 需要的格式构建 meta 字段。"""

        meta: dict[str, object] = {
            "title": title,
            "order": order,
            "hidden": hidden,
        }
        normalized_icon = ProjectRouteService._normalize_optional_icon(icon)
        if normalized_icon:
            meta["icon"] = normalized_icon
        return meta

    @staticmethod
    def _build_full_path(parent_route: str | None, route: str) -> str:
        """根据父子路由段构造展示用完整路径。"""

        if str(parent_route or "").strip():
            return f"/{str(parent_route).strip()}/{route.strip()}".replace("//", "/")
        return f"/{route.strip()}".replace("//", "/")

    @staticmethod
    def _normalize_optional_icon(value: object) -> str | None:
        """归一化可选图标名，空白值视为未配置。"""

        normalized_value = str(value or "").strip()
        return normalized_value or None

    @classmethod
    def _append_unique_icon_name(cls, target: list[str], value: object) -> None:
        """将图标名按保序去重方式加入校验列表。"""

        normalized_value = cls._normalize_optional_icon(value)
        if normalized_value and normalized_value not in target:
            target.append(normalized_value)
