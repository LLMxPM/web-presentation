"""文件功能：定义工作空间组件源码与导入用法查询工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import COMPONENT_TOOL_READ_SCOPES
from app.ai.tools.shared import build_component_import_usage, resolve_tool_context
from app.core.exceptions import AppException
from app.schemas.component import WorkspaceComponentVersionContent
from app.services.workspace_component_service import WorkspaceComponentService


def build_get_workspace_component_usage_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建工作空间组件用法查询工具。"""

    @agent_tool(show_result=False)
    async def get_workspace_component_usage(run_context: AgentToolContext, component_code: str) -> dict[str, Any]:
        """依据组件编码返回当前版本源码与导入方式。"""

        normalized_component_code = str(component_code or "").strip()
        if not normalized_component_code:
            raise AppException(status_code=400, code="COMPONENT_CODE_REQUIRED", detail="组件编码不能为空。")

        dependencies, _ = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=COMPONENT_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        workspace_id = int(dependencies["workspace_id"])

        async with session_factory() as session:
            component_service = WorkspaceComponentService(session)
            component = await component_service.get_by_code(workspace_id=workspace_id, component_code=normalized_component_code)
            if component.current_version_no <= 0:
                raise AppException(
                    status_code=409,
                    code="COMPONENT_NOT_PUBLISHED",
                    detail="组件尚未发布正式版本，不能被页面引用。",
                )
            published_version: WorkspaceComponentVersionContent = await component_service.get_version_content(
                component.id,
                component.current_version_no,
            )
            import_usage = build_component_import_usage(
                component.code,
                component.current_version_no,
                component.name,
                component.import_name,
            )
            return {
                "component_code": component.code,
                "name": component.name,
                "import_name": component.import_name,
                "component_type": component.component_type,
                "content": published_version.content,
                "import_statement": import_usage["import_statement"],
                "import_path": import_usage["import_path"],
            }

    return get_workspace_component_usage
