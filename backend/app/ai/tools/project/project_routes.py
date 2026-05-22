"""文件功能：定义统一智能体可披露的页面读取与路由树读写工具。"""

from __future__ import annotations

from typing import Any

from agno.run import RunContext
from agno.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PROJECT_TOOL_READ_SCOPES, PROJECT_TOOL_WRITE_SCOPES, extract_user_id
from app.ai.tools.shared import resolve_tool_context
from app.ai.tools.project.project_pages import build_project_page_tools
from app.ai.tools.project.project_style_config import build_project_style_config_tools
from app.schemas.page import PageListQuery
from app.schemas.project_route import (
    ProjectRouteChildItem,
    ProjectRouteChildWrite,
    ProjectRouteItemWrite,
    ProjectRouteTreeItem,
    ProjectRouteTreeWriteRequest,
)
from app.services.page_service import PageService
from app.services.project_route_service import ProjectRouteService


def build_project_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建项目工具组可用的全部工具。"""

    return [
        *build_project_style_config_tools(session_factory),
        build_list_project_pages_tool(session_factory),
        *build_project_page_tools(session_factory),
        build_get_project_route_tree_tool(session_factory),
        build_preview_project_route_tree_tool(session_factory),
        build_apply_project_route_tree_tool(session_factory),
        build_remove_project_route_node_tool(session_factory),
    ]


def build_list_project_pages_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目页面列表读取工具。"""

    @tool(show_result=False)
    async def list_project_pages(run_context: RunContext, keyword: str | None = None, limit: int = 50) -> dict[str, Any]:
        """读取当前项目下的页面摘要，供路由规划或页面定位使用。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id", "project_id"),
        )
        user_id = extract_user_id(str(claims.get("sub")))
        bounded_limit = max(1, min(int(limit), 100))
        async with session_factory() as session:
            result = await PageService(session).list(
                PageListQuery(
                    page=1,
                    page_size=bounded_limit,
                    workspace_id=int(dependencies["workspace_id"]),
                    project_id=int(dependencies["project_id"]),
                    keyword=str(keyword or "").strip() or None,
                ),
                user_id=user_id,
            )
            return {
                "total": result.total,
                "items": [
                    {
                        "page_id": item.id,
                        "page_code": item.code,
                        "title": item.title,
                        "summary": item.summary,
                        "file_type": item.file_type.value,
                        "status": item.status.value,
                        "is_in_project_route": item.is_in_project_route,
                        "route_bindings": [binding.model_dump(mode="json") for binding in item.route_bindings],
                    }
                    for item in result.items
                ],
            }

    return list_project_pages


def build_get_project_route_tree_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目路由树读取工具。"""

    @tool(show_result=False)
    async def get_project_route_tree(run_context: RunContext) -> dict[str, Any]:
        """读取当前项目完整路由树。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_READ_SCOPES,
            required_dependency_fields=("project_id",),
        )
        async with session_factory() as session:
            tree = await ProjectRouteService(session).get_tree(int(dependencies["project_id"]))
            return tree.model_dump(mode="json")

    return get_project_route_tree


def build_preview_project_route_tree_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建路由树覆盖预览工具，仅校验和返回变更摘要，不写库。"""

    @tool(show_result=False)
    async def preview_project_route_tree(run_context: RunContext, routes: list[ProjectRouteItemWrite]) -> dict[str, Any]:
        """校验拟覆盖的项目路由树并返回预览摘要。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_READ_SCOPES,
            required_dependency_fields=("project_id",),
        )
        payload = ProjectRouteTreeWriteRequest(routes=routes)
        async with session_factory() as session:
            route_service = ProjectRouteService(session)
            current_tree = await route_service.get_tree(int(dependencies["project_id"]))
            await route_service.validate_tree_payload(int(dependencies["project_id"]), payload)
            return {
                "valid": True,
                "message": "路由树预览校验通过，尚未写入数据库。",
                "current_route_count": _count_route_tree_nodes(current_tree.routes),
                "next_route_count": _count_route_write_nodes(payload.routes),
                "next_routes": payload.model_dump(mode="json")["routes"],
            }

    return preview_project_route_tree


def build_apply_project_route_tree_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建高风险路由树整树覆盖工具。"""

    @tool(show_result=False, requires_confirmation=True)
    async def apply_project_route_tree(
        run_context: RunContext,
        routes: list[ProjectRouteItemWrite],
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """以整树覆盖方式写入当前项目路由树。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("project_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        payload = ProjectRouteTreeWriteRequest(routes=routes)
        async with session_factory() as session:
            updated_tree = await ProjectRouteService(session).replace_tree(
                int(dependencies["project_id"]),
                payload,
                operator_id,
            )
            return {
                "success": True,
                "message": change_note or "项目路由树已整树覆盖。",
                "route_count": _count_route_tree_nodes(updated_tree.routes),
                "routes": updated_tree.model_dump(mode="json")["routes"],
            }

    return apply_project_route_tree


def build_remove_project_route_node_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建高风险路由节点移除工具。"""

    @tool(show_result=False, requires_confirmation=True)
    async def remove_project_route_node(run_context: RunContext, route_id: int) -> dict[str, Any]:
        """移除当前项目中的指定路由节点；分组节点会连同子页面节点一起移除。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("project_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            updated_tree = await ProjectRouteService(session).remove_route_node(
                int(dependencies["project_id"]),
                int(route_id),
                operator_id,
            )
            return {
                "success": True,
                "message": "路由节点已移除。",
                "route_count": _count_route_tree_nodes(updated_tree.routes),
                "routes": updated_tree.model_dump(mode="json")["routes"],
            }

    return remove_project_route_node


def _count_route_tree_nodes(routes: list[ProjectRouteTreeItem]) -> int:
    """统计响应路由树中的节点数量。"""

    return sum(1 + len(item.children) for item in routes)


def _count_route_write_nodes(routes: list[ProjectRouteItemWrite]) -> int:
    """统计写入路由树中的节点数量。"""

    return sum(1 + len(item.children) for item in routes)


def route_tree_item_to_write(item: ProjectRouteTreeItem) -> ProjectRouteItemWrite:
    """把响应路由节点转换为整树覆盖写入节点。"""

    if item.route_type == "group":
        return ProjectRouteItemWrite(
            route_type="group",
            route=item.route,
            order=item.order,
            icon=item.icon,
            hidden=item.hidden,
            group_title=item.group_title,
            children=[route_child_item_to_write(child) for child in item.children],
        )
    return ProjectRouteItemWrite(
        route_type="page",
        route=item.route,
        order=item.order,
        icon=item.icon,
        hidden=item.hidden,
        page_id=item.page_id,
    )


def route_child_item_to_write(item: ProjectRouteChildItem) -> ProjectRouteChildWrite:
    """把响应子路由节点转换为整树覆盖写入子节点。"""

    return ProjectRouteChildWrite(
        route=item.route,
        order=item.order,
        icon=item.icon,
        hidden=item.hidden,
        page_id=item.page_id,
    )
