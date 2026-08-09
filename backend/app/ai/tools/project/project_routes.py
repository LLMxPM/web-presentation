"""文件功能：定义内容助手内部复用的页面写入与项目路由树读写工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PROJECT_TOOL_READ_SCOPES, PROJECT_TOOL_WRITE_SCOPES, extract_user_id
from app.ai.tools.shared import resolve_tool_context
from app.ai.tools.project.project_pages import build_project_page_tools
from app.schemas.project_route import (
    ProjectRouteItemWrite,
    ProjectRouteTreeItem,
    ProjectRouteTreeWriteRequest,
)
from app.services.project_route_service import ProjectRouteService


def build_project_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建项目工具组可用的全部工具。"""

    return [
        *build_project_page_tools(session_factory),
        build_get_project_route_tree_tool(session_factory),
        build_update_project_route_tree_tool(session_factory),
    ]


def build_get_project_route_tree_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目路由树读取工具。"""

    @agent_tool(show_result=False)
    async def get_project_route_tree(run_context: AgentToolContext) -> dict[str, Any]:
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


def build_update_project_route_tree_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目路由树整树更新工具。"""

    @agent_tool(show_result=False)
    async def update_project_route_tree(
        run_context: AgentToolContext,
        routes: list[ProjectRouteItemWrite],
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """以整树覆盖方式更新当前项目路由树。"""

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("project_id",),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        payload = ProjectRouteTreeWriteRequest(routes=routes)
        async with session_factory() as session:
            project_id = int(dependencies["project_id"])
            route_service = ProjectRouteService(session)
            current_tree = await route_service.get_tree(project_id)
            updated_tree = await route_service.replace_tree(
                project_id,
                payload,
                operator_id,
            )
            return {
                "success": True,
                "message": change_note or "项目路由树已更新。",
                "previous_route_count": _count_route_tree_nodes(current_tree.routes),
                "route_count": _count_route_tree_nodes(updated_tree.routes),
                "routes": updated_tree.model_dump(mode="json")["routes"],
            }

    return update_project_route_tree


def _count_route_tree_nodes(routes: list[ProjectRouteTreeItem]) -> int:
    """统计响应路由树中的节点数量。"""

    return sum(1 + len(item.children) for item in routes)
