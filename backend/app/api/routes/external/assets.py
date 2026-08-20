"""文件功能：提供 External API v1 资源管理接口（列表、详情、内容读写、文件上传、更新、归档与批量归档）。"""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.api.routes.assets import _build_asset_response, _build_asset_responses
from app.db.session import get_db_session
from app.models.enums import AssetType
from app.schemas.asset import (
    AssetContentResponse,
    AssetContentUpdateRequest,
    AssetResponse,
    AssetUpdateRequest,
)
from app.schemas.common import PagedResponse
from app.schemas.external_api import ExternalBatchArchiveRequest, ExternalBatchArchiveResponse
from app.services.asset_service import AssetService
from app.services.business_operation_service import BusinessOperationService
from app.services.idempotency_service import IdempotencyService

router = APIRouter()


@router.get("", response_model=PagedResponse[AssetResponse])
async def list_assets(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = 1,
    page_size: int = 50,
    asset_type: AssetType | None = None,
    keyword: str | None = None,
    status: str | None = "active",
) -> PagedResponse[AssetResponse]:
    """查询指定工作空间的资源列表。"""

    asset_service = AssetService(session)
    assets, total = await asset_service.list_assets(
        workspace_id=x_workspace_id,
        asset_type=asset_type,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    responses = await _build_asset_responses(session, x_workspace_id, assets)
    return PagedResponse[AssetResponse](
        items=responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
) -> AssetResponse:
    """获取单个资源详情。"""

    asset = await AssetService(session)._get_asset_or_raise(x_workspace_id, asset_id)
    return await _build_asset_response(session, x_workspace_id, asset)


@router.get("/{asset_id}/content", response_model=AssetContentResponse)
async def get_asset_content(
    asset_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
) -> AssetContentResponse:
    """读取可编辑资源的 UTF-8 文本内容。"""

    asset_service = AssetService(session)
    asset = await asset_service._get_asset_or_raise(x_workspace_id, asset_id)
    content = await asset_service.get_asset_content(x_workspace_id, asset_id)
    return AssetContentResponse(
        id=asset.id,
        workspace_id=asset.workspace_id,
        name=asset.name,
        original_name=asset.original_name,
        asset_type=AssetType(asset.asset_type),
        content_type=asset.content_type,
        content=content,
        updated_at=asset.updated_at,
    )


@router.post("", response_model=AssetResponse)
async def upload_asset(
    request: Request,
    response: Response,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.upload"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    file: UploadFile = File(...),
    asset_type: AssetType = Form(...),
    name: str | None = Form(None),
    description: str | None = Form(None),
    tags: str | None = Form(None),
    overwrite: bool = Form(False),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AssetResponse:
    """上传资源文件（支持 Idempotency-Key 幂等保护）。"""

    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    # 流式分块计算文件 SHA256 指纹，避免大文件全量读入内存导致 OOM
    file_hasher = hashlib.sha256()
    while chunk := await file.read(65536):
        file_hasher.update(chunk)
    await file.seek(0)

    # 构造包含文件哈希与表单参数的指纹
    form_fingerprint_dict = {
        "file_hash": file_hasher.hexdigest(),
        "filename": file.filename,
        "asset_type": asset_type.value,
        "name": name,
        "description": description,
        "tags": parsed_tags,
        "overwrite": overwrite,
    }
    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=form_fingerprint_dict,
    )

    async def _operation(record_id: int | None) -> tuple[int, AssetResponse]:
        created = await AssetService(session).upload_asset(
            workspace_id=x_workspace_id,
            file=file,
            asset_type=asset_type,
            name=name,
            description=description,
            tags=parsed_tags,
            overwrite=overwrite,
            commit=False,
        )
        resp = await _build_asset_response(session, x_workspace_id, created)
        return 201, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="asset.upload",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    response.status_code = status_code
    return result if isinstance(result, AssetResponse) else AssetResponse.model_validate(result)


@router.put("/{asset_id}/content", response_model=AssetResponse)
async def update_asset_content(
    request: Request,
    asset_id: int,
    payload: AssetContentUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AssetResponse:
    """更新可编辑文本资源内容（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PUT",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, AssetResponse]:
        updated = await AssetService(session).update_asset_content(
            workspace_id=x_workspace_id,
            asset_id=asset_id,
            content=payload.content,
            change_note=payload.change_note,
            commit=False,
        )
        resp = await _build_asset_response(session, x_workspace_id, updated)
        return 200, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="asset.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, AssetResponse) else AssetResponse.model_validate(result)


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset_metadata(
    request: Request,
    asset_id: int,
    payload: AssetUpdateRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AssetResponse:
    """更新资源元数据（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="PATCH",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, AssetResponse]:
        updated = await AssetService(session).update_asset_metadata(
            workspace_id=x_workspace_id,
            asset_id=asset_id,
            name=payload.name,
            original_name=payload.original_name,
            tags=payload.tags,
            description=payload.description,
            approx_aspect_ratio=payload.approx_aspect_ratio,
            approx_aspect_ratio_provided="approx_aspect_ratio" in payload.model_fields_set,
            commit=False,
        )
        resp = await _build_asset_response(session, x_workspace_id, updated)
        return 200, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="asset.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, AssetResponse) else AssetResponse.model_validate(result)


@router.delete("/{asset_id}")
async def archive_asset(
    request: Request,
    asset_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str]:
    """归档资源（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="DELETE",
        path=request.url.path,
        json_data={"asset_id": asset_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, dict[str, str]]:
        await AssetService(session).archive_asset(workspace_id=x_workspace_id, asset_id=asset_id, commit=False)
        return 200, {"message": "资源已成功归档"}

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="asset.archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, dict) else {"message": str(result)}


@router.post("/{asset_id}/restore", response_model=AssetResponse)
async def restore_asset(
    request: Request,
    asset_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.update"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AssetResponse:
    """恢复已归档资源（支持 Idempotency-Key 幂等保护）。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data={"asset_id": asset_id},
    )

    async def _operation(record_id: int | None) -> tuple[int, AssetResponse]:
        restored = await AssetService(session).restore_asset(workspace_id=x_workspace_id, asset_id=asset_id, commit=False)
        resp = await _build_asset_response(session, x_workspace_id, restored)
        return 200, resp

    status_code, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="asset.update",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, AssetResponse) else AssetResponse.model_validate(result)


@router.post("/batch-archive", response_model=ExternalBatchArchiveResponse)
async def batch_archive_assets(
    request: Request,
    payload: ExternalBatchArchiveRequest,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("asset.archive"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ExternalBatchArchiveResponse:
    """整批原子归档多个资源。"""

    fingerprint = IdempotencyService.calculate_request_fingerprint(
        http_method="POST",
        path=request.url.path,
        json_data=payload.model_dump(mode="json"),
    )

    async def _operation(record_id: int | None) -> tuple[int, ExternalBatchArchiveResponse]:
        result = await BusinessOperationService(session).batch_archive_entities(
            workspace_id=x_workspace_id,
            entity_type="asset",
            payload=payload,
            operator_id=auth.user.id,
            commit=False,
        )
        return 200, result

    _, result = await IdempotencyService(session).execute_idempotent_operation(
        user_id=auth.user.id,
        workspace_id=x_workspace_id,
        idempotency_key=idempotency_key,
        operation="operations.batch_archive",
        fingerprint=fingerprint,
        operation_func=_operation,
    )
    return result if isinstance(result, ExternalBatchArchiveResponse) else ExternalBatchArchiveResponse.model_validate(result)
