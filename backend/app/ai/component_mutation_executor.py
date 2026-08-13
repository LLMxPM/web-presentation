"""文件功能：执行组件创建、源码编辑和需要Runtime复核的元数据外部任务。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.platform_tools import recoverable_tool_error_result
from app.ai.tools.component.component_library import (
    _component_mutation_summary,
    _ensure_component_edit_lock,
    _ensure_component_metadata_check_baseline,
    _ensure_component_workspace,
    _is_validation_passed,
)
from app.ai.tools.shared import apply_source_edits, calculate_source_hash, normalize_preview_schema_argument
from app.core.exceptions import AppException
from app.models.ai_external_task import AiComponentMutationTask
from app.models.enums import PageFileType, RecordStatus, WorkspaceComponentType
from app.schemas.component import WorkspaceComponentCreateRequest, WorkspaceComponentUpdateRequest
from app.services.code_check_service import CodeCheckService
from app.services.workspace_component_service import WorkspaceComponentService


class AiComponentMutationExecutor:
    """复核基线、写组件草稿并产出结果；CodeCheck在慢诊断前主动释放事务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(self, detail: AiComponentMutationTask, *, operator_id: int) -> dict[str, Any]:
        """按领域操作分派执行；业务校验失败以recoverable result返回。"""

        try:
            if detail.operation == "create_component":
                return await self._create(detail, operator_id=operator_id)
            if detail.operation == "apply_component_edits":
                return await self._apply_edits(detail, operator_id=operator_id)
            if detail.operation == "update_component_metadata":
                return await self._update_metadata(detail, operator_id=operator_id)
            raise AppException(status_code=400, code="AI_COMPONENT_OPERATION_INVALID", detail="未知的组件任务类型。")
        except AppException as exc:
            return recoverable_tool_error_result(
                code=exc.code,
                message=exc.detail,
                status_code=exc.status_code,
                hint="请重新读取组件详情或调整参数后再调用。",
            )

    async def _create(self, detail: AiComponentMutationTask, *, operator_id: int) -> dict[str, Any]:
        """校验并创建组件草稿。"""

        args = detail.arguments_json or {}
        component_type = WorkspaceComponentType(args.get("component_type") or WorkspaceComponentType.CONTENT_COMPONENT.value)
        preview_schema = normalize_preview_schema_argument(args.get("preview_schema"))
        validation = await CodeCheckService(self.session).check_component_code(
            workspace_id=detail.workspace_id,
            user_id=operator_id,
            content=str(args.get("content") or ""),
            preview_schema=preview_schema,
            component_type=component_type,
        )
        if not _is_validation_passed(validation):
            return _validation_error("组件校验失败，未创建草稿。", validation)
        created = await WorkspaceComponentService(self.session).create(
            WorkspaceComponentCreateRequest(
                workspace_id=detail.workspace_id,
                content=str(args.get("content") or ""),
                file_type=PageFileType.VUE,
                name=str(args.get("name") or ""),
                import_name=str(args.get("import_name") or ""),
                component_type=component_type,
                summary=args.get("summary"),
                preview_schema=preview_schema,
                status=RecordStatus.ACTIVE,
                change_note=args.get("change_note") or "AI 助手创建组件",
            ),
            operator_id,
            commit=False,
        )
        return {
            "success": True,
            "applied": True,
            "message": "组件草稿已创建，发布后才可被页面或其他组件引用。",
            "component_id": created.id,
            "component": _component_mutation_summary(created),
            "validation": validation,
        }

    async def _apply_edits(self, detail: AiComponentMutationTask, *, operator_id: int) -> dict[str, Any]:
        """在校验前后复核草稿锁，并原子保存源码编辑。"""

        args = detail.arguments_json or {}
        service = WorkspaceComponentService(self.session)
        component = await service.get(int(detail.component_id or 0), user_id=operator_id)
        _ensure_component_workspace(component.workspace_id, detail.workspace_id)
        _ensure_component_edit_lock(
            component,
            base_draft_hash=str(detail.base_draft_hash or ""),
            base_published_version_no=int(detail.base_published_version_no or 0),
        )
        edits = apply_source_edits(component.content, list(args.get("edits") or []))
        validation = await CodeCheckService(self.session).check_component_code(
            component_id=component.id,
            workspace_id=component.workspace_id,
            user_id=operator_id,
            content=edits.next_content,
        )
        if not _is_validation_passed(validation):
            return _validation_error("组件代码校验失败，未保存草稿。", validation)
        self.session.expire_all()
        refreshed = await service.get(component.id, user_id=operator_id)
        _ensure_component_edit_lock(
            refreshed,
            base_draft_hash=str(detail.base_draft_hash or ""),
            base_published_version_no=int(detail.base_published_version_no or 0),
        )
        updated = await service.update(
            component.id,
            WorkspaceComponentUpdateRequest(
                content=edits.next_content,
                change_note=args.get("change_note") or "AI 助手组件源码更新",
            ),
            operator_id,
            commit=False,
        )
        return {
            "success": True,
            "applied": True,
            "component_id": updated.id,
            "component_code": updated.code,
            "draft_hash": calculate_source_hash(updated.content),
            "base_published_version_no": updated.draft_base_version_no,
            "edits_applied": edits.applied_edit_count,
            "canonical_diff": edits.canonical_diff,
            "component": _component_mutation_summary(updated),
            "validation": validation,
        }

    async def _update_metadata(self, detail: AiComponentMutationTask, *, operator_id: int) -> dict[str, Any]:
        """复核源码、Schema及组件类型基线后更新重校验元数据。"""

        args = detail.arguments_json or {}
        service = WorkspaceComponentService(self.session)
        component = await service.get(int(detail.component_id or 0), user_id=operator_id)
        _ensure_component_workspace(component.workspace_id, detail.workspace_id)
        base_content_hash = calculate_source_hash(component.content)
        base_preview_schema = component.preview_schema
        base_component_type = component.component_type
        preview_schema = (
            component.preview_schema
            if args.get("preview_schema") is None
            else normalize_preview_schema_argument(args.get("preview_schema"))
        )
        component_type = WorkspaceComponentType(args.get("component_type") or component.component_type.value)
        validation = await CodeCheckService(self.session).check_component_code(
            component_id=component.id,
            workspace_id=component.workspace_id,
            user_id=operator_id,
            preview_schema=preview_schema,
            component_type=component_type,
        )
        if not _is_validation_passed(validation):
            return _validation_error("组件校验失败，未更新元数据。", validation)
        self.session.expire_all()
        refreshed = await service.get(component.id, user_id=operator_id)
        _ensure_component_metadata_check_baseline(
            refreshed,
            content_hash=base_content_hash,
            preview_schema=base_preview_schema,
            component_type=base_component_type,
        )
        payload: dict[str, Any] = {
            "preview_schema": preview_schema,
            "component_type": component_type,
            "change_note": args.get("change_note") or "AI 助手组件元数据更新",
        }
        for key in ("name", "import_name", "summary"):
            if args.get(key) is not None:
                payload[key] = args[key]
        updated = await service.update(
            component.id,
            WorkspaceComponentUpdateRequest(**payload),
            operator_id,
            commit=False,
        )
        return {
            "success": True,
            "applied": True,
            "component_id": updated.id,
            "message": "组件元数据已更新。",
            "component": _component_mutation_summary(updated),
            "validation": validation,
        }


def _validation_error(message: str, validation: dict[str, Any]) -> dict[str, Any]:
    """把Runtime校验失败标准化为可继续模型推理的业务结果。"""

    code = str(validation.get("code") or "AI_COMPONENT_VALIDATION_FAILED")
    return recoverable_tool_error_result(
        code=code,
        message=message,
        status_code=422,
        hint="根据validation诊断修正组件参数或源码后重试。",
        data={"validation": validation, "applied": False},
    )
