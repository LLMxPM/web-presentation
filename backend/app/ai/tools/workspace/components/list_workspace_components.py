"""文件功能：定义工作空间组件查询工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import COMPONENT_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.models.enums import WorkspaceComponentType
from app.schemas.component import WorkspaceComponentItem, WorkspaceComponentListQuery
from app.services.suggested_component_service import SuggestedComponentService
from app.services.workspace_component_service import WorkspaceComponentService


def build_list_workspace_components_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建工作空间组件查询工具。"""

    @agent_tool(show_result=False)
    async def list_workspace_components(
        run_context: AgentToolContext,
        component_type: WorkspaceComponentType | None = None,
        keyword: str | None = None,
        scope: str = "suggested",
        limit: int = 20,
    ) -> dict[str, object]:
        """查询当前工作空间可用组件，默认优先返回项目建议组件。"""

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        workspace_id = int(dependencies["workspace_id"])
        bounded_limit = max(1, min(int(limit), 100))
        normalized_scope = str(scope or "suggested").strip().lower()
        if normalized_scope not in {"suggested", "all"}:
            raise AppException(status_code=400, code="AI_TOOL_ARGUMENT_INVALID", detail="scope 只能是 suggested 或 all。")

        async with session_factory() as session:
            if normalized_scope == "all":
                return await _list_all_workspace_components(
                    session,
                    workspace_id=workspace_id,
                    component_type=component_type,
                    keyword=keyword,
                    limit=bounded_limit,
                )

            project_id = dependencies.get("project_id")
            if project_id is None:
                return await _list_all_workspace_components(
                    session,
                    workspace_id=workspace_id,
                    component_type=component_type,
                    keyword=keyword,
                    limit=bounded_limit,
                    fallback_reason="no_project_context",
                )

            suggested_items = await SuggestedComponentService(session).list_project_component_items(
                int(project_id),
                workspace_id=workspace_id,
            )
            if not suggested_items:
                return await _list_all_workspace_components(
                    session,
                    workspace_id=workspace_id,
                    component_type=component_type,
                    keyword=keyword,
                    limit=bounded_limit,
                    fallback_reason="no_project_suggested_components",
                )

            filtered_items = [
                item
                for item in suggested_items
                if _matches_component_filters(
                    {
                        "name": item.name,
                        "import_name": item.import_name,
                        "summary": item.summary,
                        "code": item.code,
                        "component_type": item.component_type.value,
                    },
                    component_type=component_type,
                    keyword=keyword,
                )
            ]
            if not filtered_items:
                return await _list_all_workspace_components(
                    session,
                    workspace_id=workspace_id,
                    component_type=component_type,
                    keyword=keyword,
                    limit=bounded_limit,
                    fallback_reason="suggested_filter_empty",
                )
            return {
                "source": "project_suggested",
                "fallback_reason": None,
                "total": len(filtered_items),
                "items": [
                    {
                        "name": item.name,
                        "import_name": item.import_name,
                        "component_type": item.component_type.value,
                        "description": item.summary,
                        "component_code": item.code,
                        "current_version_no": item.current_version_no,
                    }
                    for item in filtered_items[:bounded_limit]
                ],
            }

    return list_workspace_components


async def _list_all_workspace_components(
    session: AsyncSession,
    *,
    workspace_id: int,
    component_type: WorkspaceComponentType | None,
    keyword: str | None,
    limit: int,
    fallback_reason: str | None = None,
) -> dict[str, object]:
    """查询全工作空间已发布组件，并按工具返回结构格式化。"""

    result = await WorkspaceComponentService(session).list(
        WorkspaceComponentListQuery(
            page=1,
            page_size=limit,
            workspace_id=workspace_id,
            keyword=str(keyword or "").strip() or None,
            component_type=component_type,
            published_only=True,
        )
    )
    return {
        "source": "workspace_all",
        "fallback_reason": fallback_reason,
        "total": result.total,
        "items": [_dump_component_item(item) for item in result.items],
    }


def _dump_component_item(item: WorkspaceComponentItem) -> dict[str, str | int | None]:
    """转换工作空间组件摘要为内容助手稳定返回字段。"""

    return {
        "name": item.name,
        "import_name": item.import_name,
        "component_type": item.component_type.value,
        "description": item.summary,
        "component_code": item.code,
        "current_version_no": item.current_version_no,
    }


def _matches_component_filters(
    item: dict[str, str | None],
    *,
    component_type: WorkspaceComponentType | None,
    keyword: str | None,
) -> bool:
    """判断建议组件摘要是否匹配工具筛选条件。"""

    if component_type is not None and item.get("component_type") != component_type.value:
        return False
    normalized_keyword = str(keyword or "").strip().lower()
    if not normalized_keyword:
        return True
    search_text = " ".join(
        str(item.get(field) or "").lower()
        for field in ("name", "import_name", "summary", "code", "component_type")
    )
    return normalized_keyword in search_text
