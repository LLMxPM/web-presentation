"""文件功能：定义组件异步变更规划器（ComponentMutationPlanner），执行纯无锁慢诊断与代码校验，绝不进行数据库写入。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.component.component_library import (
    _ensure_component_edit_lock,
    _ensure_component_workspace,
    _is_validation_passed,
    normalize_preview_schema_argument,
)
from app.ai.tools.shared import apply_source_edits
from app.core.exceptions import AppException
from app.models.enums import WorkspaceComponentType, resolve_workspace_component_type
from app.services.code_check_service import CodeCheckService
from app.services.workspace_component_service import WorkspaceComponentService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ComponentMutationPlannerInput:
    """组件变更规划输入参数。"""

    operation: str  # "create_component" 或 "apply_component_edits"
    workspace_id: int
    user_id: int
    component_id: int | None = None
    base_draft_hash: str | None = None
    base_published_version_no: int | None = None
    name: str | None = None
    import_name: str | None = None
    component_type: str | None = None
    summary: str | None = None
    preview_schema: dict[str, Any] | None = None
    content: str | None = None
    edits: list[dict[str, Any]] | None = None
    change_note: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedComponentMutationResult:
    """组件变更规划结果（纯只读无锁产物）。"""

    success: bool
    operation: str
    target_component_id: int | None
    prepared_content: str
    name: str | None
    import_name: str | None
    component_type: WorkspaceComponentType
    summary: str | None
    preview_schema: dict[str, Any] | None
    change_note: str | None
    validation_result: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    message: str
    error_code: str | None = None
    error_message: str | None = None


class ComponentMutationPlanner:
    """组件变更规划器：负责 SFC 语法检查、源码 Edits 应用与场景渲染诊断，无数据库副作用。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.code_check_service = CodeCheckService(session)
        self.component_service = WorkspaceComponentService(session)

    async def plan_create(
        self,
        *,
        workspace_id: int,
        user_id: int,
        name: str,
        import_name: str,
        content: str,
        component_type: str | WorkspaceComponentType | None = None,
        summary: str | None = None,
        preview_schema: dict[str, Any] | None = None,
        change_note: str | None = None,
    ) -> PreparedComponentMutationResult:
        """规划组件创建：执行组件 SFC 语法与场景渲染诊断。"""

        if not content.strip():
            raise AppException(
                status_code=400,
                code="COMPONENT_CONTENT_REQUIRED",
                detail="创建组件时必须提供非空 content。",
            )

        try:
            resolved_type = resolve_workspace_component_type(component_type)
        except ValueError as exc:
            raise AppException(
                status_code=422,
                code="INVALID_COMPONENT_TYPE",
                detail=str(exc),
            ) from exc

        normalized_schema = normalize_preview_schema_argument(preview_schema)

        validation = await self.code_check_service.check_component_code(
            workspace_id=workspace_id,
            user_id=user_id,
            content=content,
            preview_schema=normalized_schema,
            component_type=resolved_type,
        )

        passed = _is_validation_passed(validation)
        message = "组件预检通过。" if passed else "组件代码校验失败。"
        diagnostics = list(validation.get("diagnostics") or [])

        return PreparedComponentMutationResult(
            success=passed,
            operation="create_component",
            target_component_id=None,
            prepared_content=content,
            name=name,
            import_name=import_name,
            component_type=resolved_type,
            summary=summary,
            preview_schema=normalized_schema,
            change_note=change_note,
            validation_result=validation,
            diagnostics=diagnostics,
            message=message,
            error_code=None if passed else "COMPONENT_VALIDATION_FAILED",
            error_message=None if passed else validation.get("summary") or "组件代码校验失败",
        )

    async def plan_apply_edits(
        self,
        *,
        workspace_id: int,
        user_id: int,
        component_id: int,
        base_draft_hash: str,
        base_published_version_no: int,
        edits: list[dict[str, Any]],
        change_note: str | None = None,
    ) -> PreparedComponentMutationResult:
        """规划组件更新：复核草稿锁，应用源码 diff 并执行场景渲染诊断。"""

        component = await self.component_service.get(component_id, user_id=user_id)
        _ensure_component_workspace(component.workspace_id, workspace_id)
        _ensure_component_edit_lock(
            component,
            base_draft_hash=base_draft_hash,
            base_published_version_no=base_published_version_no,
        )

        applied = apply_source_edits(component.content, edits)
        validation = await self.code_check_service.check_component_code(
            component_id=component.id,
            workspace_id=component.workspace_id,
            user_id=user_id,
            content=applied.next_content,
        )

        passed = _is_validation_passed(validation)
        message = "组件修改预检通过。" if passed else "组件修改代码校验失败。"
        diagnostics = list(validation.get("diagnostics") or [])

        return PreparedComponentMutationResult(
            success=passed,
            operation="apply_component_edits",
            target_component_id=component_id,
            prepared_content=applied.next_content,
            name=component.name,
            import_name=component.import_name,
            component_type=WorkspaceComponentType(component.component_type),
            summary=component.summary,
            preview_schema=component.preview_schema,
            change_note=change_note,
            validation_result=validation,
            diagnostics=diagnostics,
            message=message,
            error_code=None if passed else "COMPONENT_VALIDATION_FAILED",
            error_message=None if passed else validation.get("summary") or "组件代码校验失败",
        )
