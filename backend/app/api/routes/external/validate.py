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

    diagnostics = list(result.get("diagnostics") or [])
    errors = [str(item.get("message") or item) for item in diagnostics if item.get("severity") == "error"]
    warnings = [str(item.get("message") or item) for item in diagnostics if item.get("severity") == "warning"]
    if not payload.detail:
        diagnostics = diagnostics[:10]
    return ExternalEntityValidationResponse(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        mode=payload.mode,
        valid=bool(result.get("success")),
        summary=str(result.get("summary") or result.get("message") or "校验完成。"),
        errors=errors,
        warnings=warnings,
        imports=[str(item.get("module")) for item in diagnostics if item.get("module")],
        diagnostics=diagnostics if payload.detail else diagnostics[:10],
    )
