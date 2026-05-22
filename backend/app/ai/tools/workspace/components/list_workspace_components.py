"""文件功能：定义工作空间组件查询工具。"""

from __future__ import annotations

from typing import Any

from agno.run import RunContext
from agno.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import COMPONENT_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.models.enums import WorkspaceComponentType
from app.schemas.component import WorkspaceComponentListQuery
from app.services.workspace_component_service import WorkspaceComponentService


def build_list_workspace_components_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建工作空间组件查询工具。"""

    @tool(show_result=False)
    async def list_workspace_components(
        run_context: RunContext,
        component_type: WorkspaceComponentType | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, str | None]]:
        """查询当前工作空间可用组件，支持按类型和关键字过滤。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        workspace_id = int(dependencies["workspace_id"])
        bounded_limit = max(1, min(int(limit), 100))

        async with session_factory() as session:
            result = await WorkspaceComponentService(session).list(
                WorkspaceComponentListQuery(
                    page=1,
                    page_size=bounded_limit,
                    workspace_id=workspace_id,
                    keyword=keyword,
                    component_type=component_type,
                )
            )
            return [
                {
                    "name": item.name,
                    "import_name": item.import_name,
                    "description": item.summary,
                    "component_code": item.code,
                    "current_version_no": item.current_version_no,
                }
                for item in result.items
                if item.current_version_no > 0
            ]

    return list_workspace_components
