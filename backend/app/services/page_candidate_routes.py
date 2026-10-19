"""文件功能：在页面未分配 ID 时规划其保存后路由上下文，避免目录/页码读到草稿状态。"""

from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.page import Page
from app.models.project_route import ProjectRoute
from app.models.workspace import Project
from app.schemas.page import PageCopyToProjectRequest
from app.schemas.slideshow import load_slideshow_settings
from app.services.page_service import PageService
from app.services.project_route_service import ProjectRouteService


async def candidate_runtime_routes(session: AsyncSession, *, page: Page, options: dict | None) -> dict | None:
    """以保存入口相同的命名、排序和继承规则生成候选目录；不写页面、路由或虚构 ID。"""
    if not options or options.get("route_placement", "none") == "none":
        return None
    payload = PageCopyToProjectRequest(target_project_id=page.project_id, **options)
    service = ProjectRouteService(session)
    current = deepcopy(await service.build_runtime_route_config(page.project_id))
    routes = await service.route_repository.list_by_project(page.project_id)
    parent = None
    if payload.route_placement == "group":
        parent = next((row for row in routes if row.id == payload.parent_route_id and row.route_type == "group"), None)
        if parent is None:
            raise AppException(400, "PAGE_COPY_ROUTE_GROUP_INVALID", "目标路由分组不存在或不属于当前项目。")
    siblings = [row for row in routes if row.parent_id == (parent.id if parent else None)]
    segment = str(payload.route or page.code.lower()).strip()
    service._ensure_valid_route_segment(segment, source_label="候选页面路由")
    segment = PageService._build_unique_copy_route_segment(segment, siblings)
    route = ProjectRoute(route=segment, order=max((row.order for row in siblings), default=0) + 10, hidden=False,
                         transition_json=None, advance_json=None)
    project = await session.get(Project, page.project_id)
    node = service._build_runtime_page_route(route, page, load_slideshow_settings(project.slideshow_config_json))
    if parent:
        target = next(item for item in current["routes"] if item["route"] == parent.route)
        target.setdefault("children", []).append(node)
    else:
        current["routes"].append(node)
    return current
