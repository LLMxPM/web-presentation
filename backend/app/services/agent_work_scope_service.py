"""文件功能：统一校验内容助手的工作空间会话偏好、Run 焦点与项目工作集。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.ai_agent_runtime import AiAgentSession
from app.models.page import Page
from app.models.workspace import Project
from app.models.workspace_component import WorkspaceComponent
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.agent import AgentFocusRequest, AgentScopeContext


class AgentWorkScopeService:
    """把工作空间授权、项目工作集与 Run 焦点解析集中在同一安全边界。"""

    def __init__(self, session: AsyncSession, *, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def require_workspace_access(self, workspace_id: int) -> None:
        """确认工作空间存在且当前用户仍是启用成员。"""

        repository = WorkspaceRepository(self._session)
        if await repository.get_by_id(workspace_id) is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="工作空间不存在。")
        if not await repository.has_active_member(workspace_id=workspace_id, user_id=self._user_id):
            raise AppException(status_code=403, code="WORKSPACE_ACCESS_DENIED", detail="无权访问该工作空间。")

    async def validate_preferences(
        self,
        *,
        workspace_id: int,
        focus_mode: str,
        pinned_project_id: int | None,
        work_scope_mode: str,
        allowed_project_ids: list[int],
    ) -> tuple[int | None, list[int]]:
        """标准化偏好，并验证固定项目及工作集都属于会话工作空间。"""

        await self.require_workspace_access(workspace_id)
        normalized_ids = list(dict.fromkeys(int(item) for item in allowed_project_ids))
        project_ids = list(normalized_ids)
        if pinned_project_id is not None:
            project_ids.append(int(pinned_project_id))
        if project_ids:
            rows = await self._session.scalars(
                select(Project.id).where(
                    Project.id.in_(set(project_ids)),
                    Project.workspace_id == workspace_id,
                    Project.deleted_at.is_(None),
                )
            )
            if set(rows.all()) != set(project_ids):
                raise AppException(status_code=400, code="AI_SESSION_PROJECT_SCOPE_INVALID", detail="固定项目或项目工作集包含无效项目。")
        if focus_mode == "pinned_project" and pinned_project_id is None:
            raise AppException(status_code=400, code="AI_PINNED_PROJECT_REQUIRED", detail="固定项目模式必须指定 pinned_project_id。")
        if (
            focus_mode == "pinned_project"
            and work_scope_mode == "selected_projects"
            and pinned_project_id not in normalized_ids
        ):
            raise AppException(
                status_code=400,
                code="AI_PINNED_PROJECT_OUTSIDE_WORK_SCOPE",
                detail="固定项目必须包含在显式项目工作集中。",
            )
        if focus_mode != "pinned_project":
            pinned_project_id = None
        if work_scope_mode == "workspace":
            normalized_ids = []
        return pinned_project_id, normalized_ids

    async def resolve_run_focus(
        self,
        *,
        session_model: AiAgentSession,
        requested: AgentFocusRequest,
    ) -> AgentScopeContext:
        """按会话模式解析本轮不可变焦点，并校验页面与项目层级一致。"""

        await self.require_workspace_access(session_model.workspace_id)
        workspace = await WorkspaceRepository(self._session).get_by_id(session_model.workspace_id)
        workspace_name = workspace.name if workspace is not None else None
        if session_model.focus_mode == "workspace":
            return AgentScopeContext(
                scope_type="workspace",
                workspace_id=session_model.workspace_id,
                workspace_name=workspace_name,
                source="session-workspace",
            )
        if session_model.focus_mode == "pinned_project":
            project = await self._require_project(session_model.workspace_id, session_model.pinned_project_id)
            return AgentScopeContext(
                scope_type="project",
                workspace_id=session_model.workspace_id,
                workspace_name=workspace_name,
                project_id=session_model.pinned_project_id,
                project_name=project.name,
                source="session-pinned-project",
            )

        project_id = requested.project_id
        page_id = requested.page_id
        component_id = requested.component_id
        component = None
        if component_id is not None:
            component = await self._session.scalar(
                select(WorkspaceComponent).where(
                    WorkspaceComponent.id == component_id,
                    WorkspaceComponent.workspace_id == session_model.workspace_id,
                )
            )
            if component is None:
                raise AppException(status_code=404, code="WORKSPACE_COMPONENT_NOT_FOUND", detail="组件不存在或不属于当前工作空间。")
        page = None
        if page_id is not None:
            page = await self._session.scalar(select(Page).where(Page.id == page_id, Page.deleted_at.is_(None)))
            if page is None:
                raise AppException(status_code=404, code="PAGE_NOT_FOUND", detail="页面不存在。")
            if page.workspace_id != session_model.workspace_id:
                raise AppException(status_code=403, code="AI_FOCUS_WORKSPACE_MISMATCH", detail="页面不属于当前会话工作空间。")
            if project_id is not None and page.project_id != project_id:
                raise AppException(status_code=400, code="AI_FOCUS_HIERARCHY_MISMATCH", detail="页面与项目焦点不匹配。")
            project_id = page.project_id
        project = None
        if project_id is not None:
            project = await self._require_project(session_model.workspace_id, project_id)
        scope_type = requested.scope_type
        if page_id is not None:
            scope_type = "page"
        elif component_id is not None:
            scope_type = "component"
        elif project_id is not None:
            scope_type = "project"
        else:
            scope_type = "workspace"
        return AgentScopeContext(
            scope_type=scope_type,
            workspace_id=session_model.workspace_id,
            workspace_name=workspace_name,
            project_id=project_id,
            project_name=project.name if project is not None else None,
            page_id=page_id,
            page_title=page.title if page is not None else None,
            component_id=component_id,
            component_name=component.name if component is not None else None,
            source=requested.source,
        )

    async def _require_project(self, workspace_id: int, project_id: int | None) -> Project:
        """读取工作空间内未删除项目。"""

        if project_id is None:
            raise AppException(status_code=400, code="AI_PROJECT_FOCUS_REQUIRED", detail="缺少项目焦点。")
        project = await self._session.scalar(
            select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id, Project.deleted_at.is_(None))
        )
        if project is None:
            raise AppException(status_code=404, code="PROJECT_NOT_FOUND", detail="项目不存在或不属于当前工作空间。")
        return project


def project_is_in_work_scope(*, work_scope_mode: str, allowed_project_ids: list[int], project_id: int | None) -> bool:
    """判断项目是否落在 Run 固化的工作集内；空 selected_projects 明确表示不允许任何项目。"""

    if project_id is None or work_scope_mode == "workspace":
        return True
    return int(project_id) in {int(item) for item in allowed_project_ids}
