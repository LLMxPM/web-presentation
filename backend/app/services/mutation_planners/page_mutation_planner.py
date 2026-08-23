"""文件功能：定义页面异步变更规划器（PageMutationPlanner），执行纯无锁慢诊断与代码校验，绝不进行数据库写入。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.page.apply_page_edits import (
    _ensure_page_base_version,
)
from app.ai.tools.project.project_pages import (
    _has_warning_diagnostics,
    _is_validation_passed,
)
from app.ai.tools.shared import apply_source_edits
from app.core.exceptions import AppException
from app.services.code_check_service import CodeCheckService
from app.services.page_service import PageService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PageMutationPlannerInput:
    """页面变更规划输入参数。"""

    operation: str  # "create_page" 或 "apply_page_edits"
    workspace_id: int
    project_id: int | None
    user_id: int
    page_id: int | None = None
    base_version_no: int | None = None
    title: str | None = None
    summary: str | None = None
    speaker_notes: str | None = None
    page_content: str | None = None
    edits: list[dict[str, Any]] | None = None


@dataclass(frozen=True, slots=True)
class PreparedPageMutationResult:
    """页面变更规划结果（纯只读无锁产物）。"""

    success: bool
    operation: str
    target_page_id: int | None
    base_version_no: int | None
    prepared_content: str
    title: str | None
    summary: str | None
    speaker_notes: str | None
    validation_result: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    layout_analysis: dict[str, Any] | None
    code_check_summary: str | None
    message: str
    error_code: str | None = None
    error_message: str | None = None


class PageMutationPlanner:
    """页面变更规划器：负责 AST 检查、源码 Edits 应用与 Chromium 场景渲染诊断，无数据库副作用。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.code_check_service = CodeCheckService(session)
        self.page_service = PageService(session)

    async def plan_create(
        self,
        *,
        workspace_id: int,
        project_id: int,
        user_id: int,
        title: str,
        page_content: str,
        summary: str | None = None,
        speaker_notes: str | None = None,
    ) -> PreparedPageMutationResult:
        """规划页面创建：执行代码语法与场景布局诊断。"""

        if not page_content.strip():
            raise AppException(
                status_code=400,
                code="PAGE_CONTENT_REQUIRED",
                detail="创建页面时必须提供非空 page_content。",
            )

        validation_result = await self.code_check_service.check_page_code(
            page_id=None,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
            content=page_content,
        )

        passed = _is_validation_passed(validation_result)
        message = "页面已完成预检。" if passed else "页面代码校验失败。"
        diagnostics = list(validation_result.get("diagnostics") or [])
        layout_analysis = validation_result.get("layout_analysis")

        if passed and _has_warning_diagnostics(validation_result):
            message = "页面预检通过，但发现布局警告。"

        return PreparedPageMutationResult(
            success=passed,
            operation="create_page",
            target_page_id=None,
            base_version_no=None,
            prepared_content=page_content,
            title=title,
            summary=summary,
            speaker_notes=speaker_notes,
            validation_result=validation_result,
            diagnostics=diagnostics,
            layout_analysis=layout_analysis,
            code_check_summary=validation_result.get("summary"),
            message=message,
            error_code=None if passed else "PAGE_VALIDATION_FAILED",
            error_message=None if passed else validation_result.get("summary") or "页面代码校验失败",
        )

    async def plan_apply_edits(
        self,
        *,
        workspace_id: int,
        project_id: int,
        page_id: int,
        base_version_no: int,
        user_id: int,
        edits: list[dict[str, Any]],
    ) -> PreparedPageMutationResult:
        """规划页面更新：复核基线版本，应用代码 diff 并执行 Chromium 场景渲染诊断。"""

        page_detail = await self.page_service.get(page_id, user_id=user_id)
        if page_detail.project_id != project_id:
            raise AppException(
                status_code=404,
                code="OBJECT_NOT_FOUND",
                detail="页面不属于指定的项目。",
            )
        _ensure_page_base_version(page_detail.current_version_no, base_version_no)

        current_content = await self.page_service.get_version_content(
            page_id, base_version_no, user_id=user_id
        )

        applied = apply_source_edits(current_content.content, edits)
        validation_result = await self.code_check_service.check_page_code(
            page_id=page_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
            content=applied.next_content,
        )

        passed = _is_validation_passed(validation_result)
        message = "页面修改预检通过。" if passed else "页面修改代码校验失败。"
        diagnostics = list(validation_result.get("diagnostics") or [])
        layout_analysis = validation_result.get("layout_analysis")

        if passed and _has_warning_diagnostics(validation_result):
            message = "页面修改预检通过，但发现布局警告。"

        return PreparedPageMutationResult(
            success=passed,
            operation="apply_page_edits",
            target_page_id=page_id,
            base_version_no=base_version_no,
            prepared_content=applied.next_content,
            title=page_detail.title,
            summary=page_detail.summary,
            speaker_notes=page_detail.speaker_notes,
            validation_result=validation_result,
            diagnostics=diagnostics,
            layout_analysis=layout_analysis,
            code_check_summary=validation_result.get("summary"),
            message=message,
            error_code=None if passed else "PAGE_VALIDATION_FAILED",
            error_message=None if passed else validation_result.get("summary") or "页面代码校验失败",
        )
