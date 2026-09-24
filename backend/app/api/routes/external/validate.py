"""文件功能：提供页面与组件实体当前内容、候选内容和结构化编辑校验接口。"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.schemas.external_api import ExternalEntityValidationRequest, ExternalEntityValidationResponse
from app.services.code_check_service import CodeCheckService
from app.services.page_service import PageService
from app.services.validation_result import is_validation_passed
from app.services.workspace_component_service import WorkspaceComponentService

router = APIRouter()


@router.post("/entity", response_model=ExternalEntityValidationResponse)
async def validate_entity(
    payload: ExternalEntityValidationRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("validate.entity"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalEntityValidationResponse:
    """校验页面或组件当前内容、完整候选内容或结构化编辑候选内容。"""

    required_scope = "page:read" if payload.entity_type == "page" else "component:read"
    if not auth.has_scope(required_scope):
        raise AppException(
            status_code=403,
            code="INSUFFICIENT_SCOPE",
            detail=f"校验 {payload.entity_type} 需要 {required_scope} 权限 Scope。",
            data={"required_scopes": [required_scope]},
        )

    if payload.entity_id is None:
        raise AppException(status_code=400, code="VALIDATION_TARGET_REQUIRED", detail="实体校验必须提供 entity_id。")

    code_check = CodeCheckService(session)
    if payload.entity_type == "page":
        page = await PageService(session).get(payload.entity_id, user_id=auth.user.id)
        await auth.ensure_workspace_access(page.workspace_id, session)
        if payload.mode == "content" and payload.source_code is None:
            raise AppException(status_code=400, code="VALIDATION_CONTENT_REQUIRED", detail="content 模式必须提供 source_code。")
        if payload.mode == "edits" and not payload.edits:
            raise AppException(status_code=400, code="VALIDATION_EDITS_REQUIRED", detail="edits 模式必须提供 edits。")
        result = await code_check.check_page_code(
            page_id=page.id,
            user_id=auth.user.id,
            workspace_id=page.workspace_id,
            content=payload.source_code if payload.mode == "content" else None,
            edits=payload.edits if payload.mode == "edits" else None,
        )
    else:
        component = await WorkspaceComponentService(session).get(payload.entity_id, user_id=auth.user.id)
        await auth.ensure_workspace_access(component.workspace_id, session)
        if payload.mode == "content" and payload.source_code is None:
            raise AppException(status_code=400, code="VALIDATION_CONTENT_REQUIRED", detail="content 模式必须提供 source_code。")
        if payload.mode == "edits" and not payload.edits:
            raise AppException(status_code=400, code="VALIDATION_EDITS_REQUIRED", detail="edits 模式必须提供 edits。")
        preview_schema: str | None = None
        if payload.preview_schema is not None:
            preview_schema = json.dumps(payload.preview_schema, ensure_ascii=False)
        result = await code_check.check_component_code(
            component_id=component.id,
            workspace_id=component.workspace_id,
            user_id=auth.user.id,
            content=payload.source_code if payload.mode == "content" else None,
            edits=payload.edits if payload.mode == "edits" else None,
            preview_schema=preview_schema,
        )

    # 响应契约要求 diagnostics 为 dict 列表；一次性过滤后统一按 dict 读取。
    diagnostics: list[dict[str, Any]] = [
        item for item in (result.get("diagnostics") or []) if isinstance(item, dict)
    ]
    status = str(result.get("status") or "")
    # 页面默认要求 render 阶段通过；组件只做契约 + 编译。
    valid = is_validation_passed(result, require_render=payload.entity_type == "page")
    errors = [str(item.get("message") or item) for item in diagnostics if item.get("severity") == "error"]
    warnings = [str(item.get("message") or item) for item in diagnostics if item.get("severity") == "warning"]
    error_code: str | None = None
    if status == "unavailable":
        # 执行不可用时把基础设施错误码与说明提升到顶层，避免调用方只看到笼统失败。
        infrastructure = [item for item in diagnostics if item.get("source") == "infrastructure"]
        error_code = next(
            (str(item["code"]) for item in infrastructure if item.get("code")),
            "VALIDATION_UNAVAILABLE",
        )
        for item in infrastructure:
            message = str(item.get("message") or item)
            if message not in errors:
                errors.append(message)
    if not payload.detail:
        diagnostics = diagnostics[:10]
    summary = str(result.get("summary") or result.get("message") or "校验完成。")
    if status == "unavailable" and "不可用" not in summary:
        summary = f"校验执行不可用（{error_code or 'VALIDATION_UNAVAILABLE'}）：{summary}"
    return ExternalEntityValidationResponse(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        mode=payload.mode,
        valid=valid,
        status=status or None,
        retryable=bool(result.get("retryable")),
        error_code=error_code,
        summary=summary,
        errors=errors,
        warnings=warnings,
        imports=[str(item["module"]) for item in diagnostics if item.get("module")],
        diagnostics=diagnostics,
    )
