"""文件功能：根据智能体业务 scope 构建 Agno 运行时上下文。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import AgentRuntimeContext
from app.ai.authoring_canvas import resolve_authoring_canvas_size
from app.schemas.agent import AgentScopeContext
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService


async def build_agent_runtime_context(*, session: AsyncSession, scope: AgentScopeContext) -> AgentRuntimeContext:
    """按业务范围补齐页面或组件信息，供 Agent 提示词与工具依赖使用。"""

    page_item = await PageService(session).get(scope.page_id) if scope.page_id is not None else None
    component_item = await WorkspaceComponentService(session).get(scope.component_id) if scope.component_id is not None else None
    project_id = scope.project_id or (page_item.project_id if page_item else None)
    project_item = await ProjectService(session).get(project_id) if project_id is not None else None
    authoring_canvas = resolve_authoring_canvas_size(
        page_width=project_item.page_width if project_item else None,
        page_height=project_item.page_height if project_item else None,
        base_font_size=project_item.base_font_size if project_item else None,
    )
    return AgentRuntimeContext(
        scope_type=scope.scope_type,
        workspace_id=scope.workspace_id,
        project_id=project_id,
        page_id=scope.page_id,
        component_id=scope.component_id,
        source=scope.source,
        authoring_width=authoring_canvas.authoring_width if authoring_canvas else None,
        authoring_height=authoring_canvas.authoring_height if authoring_canvas else None,
        style_spec_markdown=project_item.style_spec_markdown if project_item else None,
        page_title=page_item.title if page_item else None,
        page_summary=page_item.summary if page_item else None,
        page_code=page_item.code if page_item else None,
        page_content=page_item.page_content if page_item else None,
        file_type=page_item.file_type.value if page_item else None,
        component_code=component_item.code if component_item else None,
        component_name=component_item.name if component_item else None,
    )
