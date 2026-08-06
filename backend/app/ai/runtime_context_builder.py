"""文件功能：根据智能体业务 scope 构建平台运行时上下文。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent import AgentRuntimeContext
from app.models.workspace import Project, Workspace
from app.models.workspace_component import WorkspaceComponent
from app.schemas.agent import AgentScopeContext
from app.services.page_service import PageService
from app.services.project_service import ProjectService


async def build_agent_runtime_context(
    *,
    session: AsyncSession,
    scope: AgentScopeContext,
    work_scope_mode: str = "workspace",
    allowed_project_ids: list[int] | tuple[int, ...] = (),
    focus_version: int = 0,
) -> AgentRuntimeContext:
    """只补齐 Run 所需的轻量焦点信息，重内容一律由查询工具按需读取。"""

    workspace_name = await session.scalar(select(Workspace.name).where(Workspace.id == scope.workspace_id))
    page_item = await PageService(session).get(scope.page_id) if scope.page_id is not None else None
    project_id = scope.project_id or (page_item.project_id if page_item else None)
    project_item = await ProjectService(session).get(project_id) if project_id is not None else None
    component_name = (
        await session.scalar(select(WorkspaceComponent.name).where(WorkspaceComponent.id == scope.component_id))
        if scope.component_id is not None
        else None
    )
    allowed_rows = []
    if work_scope_mode == "selected_projects" and allowed_project_ids:
        result = await session.execute(
            select(Project.id, Project.name).where(
                Project.workspace_id == scope.workspace_id,
                Project.id.in_({int(item) for item in allowed_project_ids}),
            )
        )
        allowed_rows = sorted(result.all(), key=lambda item: list(allowed_project_ids).index(item.id))
    return AgentRuntimeContext(
        scope_type=scope.scope_type,
        workspace_id=scope.workspace_id,
        workspace_name=scope.workspace_name or workspace_name,
        project_id=project_id,
        project_name=scope.project_name or (project_item.name if project_item else None),
        page_id=scope.page_id,
        component_id=scope.component_id,
        source=scope.source,
        work_scope_mode=work_scope_mode,
        allowed_project_ids=tuple(int(item) for item in allowed_project_ids),
        allowed_projects=tuple((int(item.id), str(item.name)) for item in allowed_rows),
        focus_version=focus_version,
        page_width=project_item.page_width if project_item else None,
        page_height=project_item.page_height if project_item else None,
        base_font_size=project_item.base_font_size if project_item else None,
        style_spec_markdown=None,
        page_title=scope.page_title or (page_item.title if page_item else None),
        page_summary=None,
        page_speaker_notes=None,
        page_code=None,
        page_content=None,
        file_type=None,
        component_code=None,
        component_name=scope.component_name or component_name,
        suggested_components=(),
        suggested_reference_assets=(),
    )
