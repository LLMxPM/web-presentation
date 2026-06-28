"""文件功能：定义统一智能体可披露的页面结构化 Edits 写回工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PAGE_TOOL_WRITE_SCOPES, extract_user_id
from app.ai.tools.shared import SourceEditInput, apply_source_edits, resolve_tool_context
from app.core.exceptions import AppException
from app.schemas.page import PageItem, PageUpdateRequest
from app.services.code_check_service import CodeCheckService, build_code_check_failed_result
from app.services.page_service import PageService


def build_apply_page_edits_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建页面结构化 Edits 更新工具，负责直接写回页面并自动生成版本。"""

    @agent_tool(show_result=False)
    async def apply_page_edits(
        run_context: AgentToolContext,
        page_id: int,
        edits: list[SourceEditInput],
        base_version_no: int,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        """对指定页面应用结构化 edits，并自动保存为新版本。"""

        dependencies, claims = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=PAGE_TOOL_WRITE_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        target_page_id = int(page_id)
        operator_id = extract_user_id(str(claims.get("sub")))

        async with session_factory() as session:
            page_service = PageService(session)
            current_page = await page_service.get(target_page_id, user_id=operator_id)
            _ensure_page_in_context(current_page, dependencies)
            _ensure_page_base_version(current_page.current_version_no, base_version_no)
            try:
                edit_result = apply_source_edits(current_page.page_content, edits)
            except AppException as exc:
                return build_code_check_failed_result(code=exc.code, message=exc.detail, source="edits")
            validation_result = await CodeCheckService(session).check_page_code(
                page_id=target_page_id,
                workspace_id=current_page.workspace_id,
                user_id=operator_id,
                content=edit_result.next_content,
            )
            validation_result = _with_apply_validation_metadata(
                validation_result,
                canonical_diff=edit_result.canonical_diff,
                edits_applied=edit_result.applied_edit_count,
                message="页面代码校验失败，未保存页面版本。",
            )
            if not _is_validation_passed(validation_result):
                return validation_result
            updated_page = await page_service.update(
                target_page_id,
                PageUpdateRequest(
                    page_content=edit_result.next_content,
                    change_note=change_note or "AI 助手页面更新",
                ),
                operator_id,
            )
            response = {
                "success": True,
                "message": "页面代码已更新并生成新版本。",
                "page_id": updated_page.id,
                "page_code": updated_page.code,
                "version_no": updated_page.current_version_no,
                "edits_applied": edit_result.applied_edit_count,
                "canonical_diff": edit_result.canonical_diff,
                "diagnostics": _extract_diagnostics(validation_result),
                "code_check_summary": validation_result.get("summary"),
            }
            if _has_warning_diagnostics(response):
                response["message"] = "页面代码已更新并生成新版本，但发现布局警告。"
            return response

    return apply_page_edits


def _is_validation_passed(result: dict[str, Any]) -> bool:
    """判断 Runtime 代码检查结果是否通过。"""

    return bool(result.get("success") is True or result.get("status") == "passed")


def _with_apply_validation_metadata(
    result: dict[str, Any],
    *,
    canonical_diff: str,
    edits_applied: int,
    message: str,
) -> dict[str, Any]:
    """为 apply 内置校验结果补齐 edits 元数据和失败提示。"""

    enriched = dict(result)
    enriched["canonical_diff"] = enriched.get("canonical_diff") or canonical_diff
    enriched["edits_applied"] = edits_applied
    if not _is_validation_passed(enriched):
        enriched["success"] = False
        enriched["status"] = "failed"
        enriched["message"] = message
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


def _ensure_page_in_context(page_item: PageItem, dependencies: dict[str, Any]) -> None:
    """确保显式写入的页面不越过当前工具令牌绑定的工作空间或项目边界。"""

    workspace_id = _coerce_optional_int(dependencies.get("workspace_id"))
    project_id = _coerce_optional_int(dependencies.get("project_id"))
    if workspace_id is not None and page_item.workspace_id != workspace_id:
        raise AppException(
            status_code=403,
            code="AI_TOOL_CONTEXT_MISMATCH",
            detail="目标页面不属于当前工具上下文绑定的工作空间。",
        )
    if project_id is not None and page_item.project_id != project_id:
        raise AppException(
            status_code=403,
            code="AI_TOOL_CONTEXT_MISMATCH",
            detail="目标页面不属于当前工具上下文绑定的项目。",
        )


def _ensure_page_base_version(current_version_no: int, base_version_no: int) -> None:
    """校验页面乐观锁，避免基于旧版本覆盖最新页面。"""

    if int(current_version_no) == int(base_version_no):
        return
    raise AppException(
        status_code=409,
        code="AI_PAGE_BASE_VERSION_STALE",
        detail="页面版本已变化，请重新读取页面源码后再修改。",
    )


def _coerce_optional_int(value: Any) -> int | None:
    """把工具依赖中的整数字段安全转换为整数。"""

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
