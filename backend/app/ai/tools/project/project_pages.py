"""文件功能：定义统一智能体可披露的页面创建与页面元数据维护工具。"""

from __future__ import annotations

from typing import Any

from pydantic_ai import CallDeferred

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PROJECT_TOOL_WRITE_SCOPES, extract_user_id
from app.ai.page_mutation_enqueue import enqueue_page_mutation
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.models.enums import PageFileType, RecordStatus
from app.schemas.page import PageCreateRequest, PageUpdateRequest
from app.services.code_check_service import CodeCheckService
from app.services.page_service import PageService


def build_project_page_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Any]:
    """构建项目页面结构管理工具列表。"""

    return [
        build_create_project_page_tool(session_factory),
        build_update_page_metadata_tool(session_factory),
    ]


def build_create_project_page_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建项目页面创建工具。"""

    @agent_tool(show_result=False, sequential=True)
    async def create_project_page(
        run_context: AgentToolContext,
        title: str,
        page_content: str,
        summary: str | None = None,
        speaker_notes: str | None = None,
    ) -> dict[str, Any]:
        """在当前项目创建页面；page_content 必填，可同时写入演讲者备注。"""

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
        tool_call_id = str(dependencies.get("current_tool_call_id") or "").strip()
        if tool_call_id:
            enqueued = await enqueue_page_mutation(
                session_factory,
                run_id=run_context.run_id,
                session_id=run_context.session_id,
                run_step=int(dependencies.get("current_run_step") or 0),
                tool_call_id=tool_call_id,
                operation="create_page",
                workspace_id=int(dependencies["workspace_id"]),
                project_id=int(dependencies["project_id"]),
            )
            raise CallDeferred(metadata=enqueued.as_metadata())
        async with session_factory() as session:
            validation_result = await CodeCheckService(session).check_page_code(
                page_id=None,
                project_id=int(dependencies["project_id"]),
                workspace_id=int(dependencies["workspace_id"]),
                user_id=operator_id,
                content=normalized_page_content,
            )
            if not _is_validation_passed(validation_result):
                return _with_create_validation_failure_message(validation_result)

            created = await PageService(session).create(
                PageCreateRequest(
                    workspace_id=int(dependencies["workspace_id"]),
                    project_id=int(dependencies["project_id"]),
                    title=normalized_title,
                    summary=summary,
                    speaker_notes=speaker_notes,
                    page_content=normalized_page_content,
                    file_type=PageFileType.VUE,
                    status=RecordStatus.ACTIVE,
                ),
                operator_id,
            )
            response = {
                "success": True,
                "message": "页面已创建。",
                "page_id": created.id,
                "page_code": created.code,
                "title": created.title,
                "summary": created.summary,
                "speaker_notes": created.speaker_notes,
                "project_id": created.project_id,
                "version_no": created.current_version_no,
                "diagnostics": _extract_diagnostics(validation_result),
                "code_check_summary": validation_result.get("summary"),
            }
            if _has_warning_diagnostics(response):
                response["message"] = "页面已创建，但发现布局警告。"
            return response

    return create_project_page


def build_update_page_metadata_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建页面标题与说明维护工具。"""

    @agent_tool(show_result=False)
    async def update_page_metadata(
        run_context: AgentToolContext,
        page_id: int,
        title: str | None = None,
        summary: str | None = None,
        speaker_notes: str | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """修改当前项目内页面的名称、说明或演讲者备注，不修改页面源码。"""

        if title is None and summary is None and speaker_notes is None:
            raise AppException(
                status_code=400,
                code="AI_PAGE_METADATA_REQUIRED",
                detail="修改页面元数据时，title、summary 与 speaker_notes 至少提供其一。",
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
            update_payload: dict[str, Any] = {"change_note": change_note or "AI 助手页面元数据更新"}
            if title is not None:
                update_payload["title"] = normalized_title
            if summary is not None:
                update_payload["summary"] = summary
            if speaker_notes is not None:
                update_payload["speaker_notes"] = speaker_notes
            updated = await page_service.update(
                int(page_id),
                PageUpdateRequest(**update_payload),
                operator_id,
            )
            return {
                "success": True,
                "message": "页面名称或说明已更新。",
                "page_id": updated.id,
                "page_code": updated.code,
                "title": updated.title,
                "summary": updated.summary,
                "speaker_notes": updated.speaker_notes,
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


def _is_validation_passed(result: dict[str, Any]) -> bool:
    """判断创建前页面代码检查是否通过。"""

    return bool(result.get("success") is True or result.get("status") == "passed")


def _with_create_validation_failure_message(result: dict[str, Any]) -> dict[str, Any]:
    """为创建前校验失败结果补充不会落库的提示。"""

    enriched = dict(result)
    enriched["success"] = False
    enriched["status"] = "failed"
    enriched["message"] = "页面代码校验失败，未创建页面。"
    return enriched


def _extract_diagnostics(result: dict[str, Any]) -> list[Any]:
    """从代码检查结果中读取诊断列表。"""

    diagnostics = result.get("diagnostics")
    return list(diagnostics) if isinstance(diagnostics, list) else []


def _has_warning_diagnostics(result: dict[str, Any]) -> bool:
    """判断工具响应中是否存在 warning 级别诊断。"""

    return any(
        isinstance(item, dict) and item.get("severity") == "warning"
        for item in _extract_diagnostics(result)
    )
