"""文件功能：定义统一智能体可披露的页面创建与页面元数据维护工具。"""

from __future__ import annotations

from typing import Any

from agno.run import RunContext
from agno.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PROJECT_TOOL_WRITE_SCOPES, extract_user_id
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.models.enums import PageFileType, RecordStatus
from app.schemas.page import PageCreateRequest, PageUpdateRequest
from app.services.page_service import PageService


def build_project_page_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建项目页面结构管理工具列表。"""

    return [
        build_create_project_page_tool(session_factory),
        build_update_page_metadata_tool(session_factory),
    ]


def build_create_project_page_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目页面创建工具。"""

    @tool(show_result=False)
    async def create_project_page(
        run_context: RunContext,
        title: str,
        page_content: str,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """在当前项目创建页面；page_content 必填，建议先提供可运行的占位 Vue SFC。"""

        normalized_title = str(title or "").strip()
        normalized_page_content = str(page_content or "")
        if not normalized_title:
            raise AppException(status_code=400, code="AI_PAGE_TITLE_REQUIRED", detail="页面标题不能为空。")
        if not normalized_page_content.strip():
            raise AppException(
                status_code=400,
                code="AI_PAGE_CONTENT_REQUIRED",
                detail="创建页面时必须提供非空 page_content。建议先写入结构清晰、可运行的占位 Vue SFC，后续再切换到页面上下文细化。",
            )

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id", "project_id"),
        )
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            created = await PageService(session).create(
                PageCreateRequest(
                    workspace_id=int(dependencies["workspace_id"]),
                    project_id=int(dependencies["project_id"]),
                    title=normalized_title,
                    summary=summary,
                    page_content=normalized_page_content,
                    file_type=PageFileType.VUE,
                    status=RecordStatus.ACTIVE,
                ),
                operator_id,
            )
            return {
                "success": True,
                "message": "页面已创建。",
                "page_id": created.id,
                "page_code": created.code,
                "title": created.title,
                "summary": created.summary,
                "project_id": created.project_id,
                "version_no": created.current_version_no,
            }

    return create_project_page


def build_update_page_metadata_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建页面标题与说明维护工具。"""

    @tool(show_result=False)
    async def update_page_metadata(
        run_context: RunContext,
        page_id: int,
        title: str | None = None,
        summary: str | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """修改当前项目内页面的名称或说明，不修改页面源码。"""

        if title is None and summary is None:
            raise AppException(
                status_code=400,
                code="AI_PAGE_METADATA_REQUIRED",
                detail="修改页面元数据时，title 与 summary 至少提供其一。",
            )
        normalized_title = None if title is None else str(title).strip()
        if title is not None and not normalized_title:
            raise AppException(status_code=400, code="AI_PAGE_TITLE_REQUIRED", detail="页面标题不能为空。")

        dependencies, claims = await resolve_tool_context(session_factory,
            run_context,
            required_scopes=PROJECT_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id", "project_id"),
        )
        workspace_id = int(dependencies["workspace_id"])
        project_id = int(dependencies["project_id"])
        operator_id = extract_user_id(str(claims.get("sub")))
        async with session_factory() as session:
            page_service = PageService(session)
            current_page = await page_service.get(int(page_id))
            _ensure_page_scope(
                page_workspace_id=current_page.workspace_id,
                page_project_id=current_page.project_id,
                expected_workspace_id=workspace_id,
                expected_project_id=project_id,
            )
            updated = await page_service.update(
                int(page_id),
                PageUpdateRequest(
                    title=normalized_title,
                    summary=summary,
                    change_note=change_note or "AI 助手页面元数据更新",
                ),
                operator_id,
            )
            return {
                "success": True,
                "message": "页面名称或说明已更新。",
                "page_id": updated.id,
                "page_code": updated.code,
                "title": updated.title,
                "summary": updated.summary,
                "project_id": updated.project_id,
                "version_no": updated.current_version_no,
            }

    return update_page_metadata


def _ensure_page_scope(
    *,
    page_workspace_id: int | None,
    page_project_id: int | None,
    expected_workspace_id: int,
    expected_project_id: int,
) -> None:
    """校验页面属于当前项目，避免跨项目维护页面元数据。"""

    if page_workspace_id != expected_workspace_id or page_project_id != expected_project_id:
        raise AppException(
            status_code=403,
            code="AI_PAGE_SCOPE_DENIED",
            detail="页面不属于当前项目，拒绝修改页面元数据。",
        )
