"""文件功能：处理工作空间资源的上传、内容写入、归档、复制和删除管理。"""

import json
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_list_query, require_workspace_access
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetRole, AssetType, RecordStatus
from app.schemas.asset import (
    AssetArchiveRequest,
    AssetBatchArchiveRequest,
    AssetBatchDeleteRequest,
    AssetBatchOperationResponse,
    AssetContentCreateRequest,
    AssetContentPreviewRequest,
    AssetContentPreviewResponse,
    AssetContentResponse,
    AssetContentUpdateRequest,
    AssetCopyRequest,
    AssetPackageExportRequest,
    AssetPackageImportResult,
    AssetReferenceSummary,
    AssetResponse,
    AssetRestoreRequest,
    AssetUpdateRequest,
)
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.release import PreviewArtifactResponse
from app.services.asset_package_service import AssetPackageService
from app.services.asset_service import AssetService
from app.services.asset_preview_service import AssetPreviewService
from app.services.auth_service import AuthContext
from app.services.workspace_font_service import WorkspaceFontService

router = APIRouter(dependencies=[Depends(require_workspace_access)])


async def _build_asset_response(session: AsyncSession, workspace_id: int, asset: WorkspaceAsset) -> AssetResponse:
    """把资源 ORM 模型转换为带公开 URL 与字体摘要的接口响应。"""

    settings = get_settings()
    response = AssetResponse.model_validate(asset)
    response.url = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}/{asset.file_hash}"
    enriched_payload = await WorkspaceFontService(session).enrich_asset_payloads(
        workspace_id,
        [asset],
        [response.model_dump()],
    )
    return AssetResponse.model_validate(enriched_payload[0])


async def _build_asset_responses(
    session: AsyncSession,
    workspace_id: int,
    assets: list[WorkspaceAsset],
) -> list[AssetResponse]:
    """批量转换资源响应，避免列表接口重复散落 URL 与字体增强逻辑。"""

    settings = get_settings()
    payloads = []
    for asset in assets:
        response = AssetResponse.model_validate(asset)
        response.url = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}/{asset.file_hash}"
        payloads.append(response.model_dump())
    enriched_payloads = await WorkspaceFontService(session).enrich_asset_payloads(workspace_id, assets, payloads)
    return [AssetResponse.model_validate(item) for item in enriched_payloads]


@router.post("/workspaces/{workspace_id}/assets/upload", response_model=AssetResponse)
async def upload_asset_file(
    workspace_id: int,
    file: Annotated[UploadFile, File(...)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    asset_type: Annotated[AssetType, Form()] = AssetType.ICON,
    tags: Annotated[str, Form()] = "[]",
    name: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    overwrite: Annotated[bool, Form()] = False,
) -> AssetResponse:
    """上传资源到工作空间；覆盖已有资源时自动生成历史归档副本。"""

    try:
        tag_list = json.loads(tags)
    except Exception:
        tag_list = []

    service = AssetService(session)
    asset = await service.upload_asset(
        workspace_id,
        file,
        asset_type,
        tag_list,
        name,
        description,
        overwrite=overwrite,
    )
    return await _build_asset_response(session, workspace_id, asset)


@router.get("/workspaces/{workspace_id}/assets", response_model=PagedResponse[AssetResponse])
async def list_workspace_assets(
    workspace_id: int,
    query: Annotated[ListQuery, Depends(get_list_query)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    asset_type: AssetType | None = None,
    exclude_asset_type: AssetType | None = None,
    asset_role: AssetRole | None = None,
    render_type: AssetType | None = None,
    tag: str | None = None,
    include_history: bool = False,
    history_only: Annotated[bool, Query()] = False,
) -> PagedResponse[AssetResponse]:
    """查看工作空间资源；默认只返回 active 普通资源，可切换 archived/history。"""

    assets, total = await AssetService(session).list_assets(
        workspace_id,
        asset_type=asset_type,
        exclude_asset_type=exclude_asset_type,
        asset_role=asset_role,
        render_type=render_type,
        status=query.status if query.status is not None else RecordStatus.ACTIVE,
        include_history=include_history,
        history_only=history_only,
        keyword=query.keyword,
        tag=tag,
        page=query.page,
        page_size=query.page_size,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    items = await _build_asset_responses(session, workspace_id, assets)
    return PagedResponse[AssetResponse](
        items=items,
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


@router.get("/workspaces/{workspace_id}/assets/tags", response_model=list[str])
async def list_workspace_asset_tags(
    workspace_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    asset_type: AssetType | None = None,
    exclude_asset_type: AssetType | None = None,
    status: RecordStatus | None = RecordStatus.ACTIVE,
    include_history: bool = False,
    history_only: Annotated[bool, Query()] = False,
) -> list[str]:
    """按资源类型、状态和历史范围汇总工作空间资源标签。"""

    return await AssetService(session).list_tags(
        workspace_id,
        asset_type=asset_type,
        exclude_asset_type=exclude_asset_type,
        status=status,
        include_history=include_history,
        history_only=history_only,
    )


@router.post("/workspaces/{workspace_id}/assets/content", response_model=AssetResponse)
async def create_workspace_asset_content(
    workspace_id: int,
    request: AssetContentCreateRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """通过文本内容创建 SVG 图标、SVG 图片、Draw.io、Mermaid、Chart 或 Formula 资源。"""

    asset = await AssetService(session).create_content_asset(
        workspace_id,
        asset_type=request.asset_type,
        name=request.name,
        original_name=request.original_name,
        content=request.content,
        tags=request.tags,
        description=request.description,
        approx_aspect_ratio=request.approx_aspect_ratio,
        aspect_ratio_source="manual",
    )
    return await _build_asset_response(session, workspace_id, asset)


@router.get("/workspaces/{workspace_id}/assets/{asset_id}/content", response_model=AssetContentResponse)
async def get_workspace_asset_content(
    workspace_id: int,
    asset_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetContentResponse:
    """读取可编辑资源的文本内容。"""

    service = AssetService(session)
    asset = await service._get_asset_or_raise(workspace_id, asset_id)
    content = await service.get_asset_content(workspace_id, asset_id)
    return AssetContentResponse(asset=await _build_asset_response(session, workspace_id, asset), content=content)


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/preview-artifact", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_workspace_asset_preview_artifact(
    workspace_id: int,
    asset_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """创建资源专属 Runtime 预览 artifact。"""

    tenant_id = f"tenant_{current.user.id}"
    return await AssetPreviewService(session).create_preview_artifact(
        workspace_id=workspace_id,
        asset_id=asset_id,
        tenant_id=tenant_id,
    )


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/content/preview", response_model=AssetContentPreviewResponse)
async def preview_workspace_asset_content_diff(
    workspace_id: int,
    asset_id: int,
    request: AssetContentPreviewRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetContentPreviewResponse:
    """预览资源内容写入 diff。"""

    result = await AssetService(session).preview_content_update(workspace_id, asset_id, request.content)
    return AssetContentPreviewResponse.model_validate(result)


@router.put("/workspaces/{workspace_id}/assets/{asset_id}/content", response_model=AssetResponse)
async def update_workspace_asset_content(
    workspace_id: int,
    asset_id: int,
    request: AssetContentUpdateRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """写入可编辑资源内容；写入前自动生成历史归档副本。"""

    asset = await AssetService(session).update_asset_content(
        workspace_id,
        asset_id,
        request.content,
        change_note=request.change_note,
    )
    return await _build_asset_response(session, workspace_id, asset)


@router.put("/workspaces/{workspace_id}/assets/{asset_id}", response_model=AssetResponse)
async def update_workspace_asset(
    workspace_id: int,
    asset_id: int,
    request: AssetUpdateRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """更新资源元数据（逻辑名、展示文件名、描述、标签或近似比例）。"""

    asset = await AssetService(session).update_asset_metadata(
        workspace_id,
        asset_id,
        request.name,
        request.original_name,
        request.tags,
        request.description,
        approx_aspect_ratio=request.approx_aspect_ratio,
        approx_aspect_ratio_provided="approx_aspect_ratio" in request.model_fields_set,
        aspect_ratio_source="manual",
    )
    return await _build_asset_response(session, workspace_id, asset)


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/replace", response_model=AssetResponse)
async def replace_workspace_asset_file(
    workspace_id: int,
    asset_id: int,
    file: Annotated[UploadFile, File(...)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """使用新文件替换指定资源，保留逻辑名和引用关系，并生成历史副本。"""

    asset = await AssetService(session).replace_asset_file(workspace_id, asset_id, file)
    return await _build_asset_response(session, workspace_id, asset)


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/copy", response_model=AssetResponse)
async def copy_workspace_asset(
    workspace_id: int,
    asset_id: int,
    request: AssetCopyRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """复制资源记录并复用物理文件指针。"""

    asset = await AssetService(session).copy_asset(
        workspace_id,
        asset_id,
        name=request.name,
        original_name=request.original_name,
        tags=request.tags,
        description=request.description,
        status=request.status,
        archive_reason=request.archive_reason,
    )
    return await _build_asset_response(session, workspace_id, asset)


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/archive", response_model=AssetResponse)
async def archive_workspace_asset(
    workspace_id: int,
    asset_id: int,
    request: AssetArchiveRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """归档资源；归档资源仍保持公开访问和引用解析能力。"""

    asset = await AssetService(session).archive_asset(workspace_id, asset_id, archive_reason=request.archive_reason)
    return await _build_asset_response(session, workspace_id, asset)


@router.post("/workspaces/{workspace_id}/assets/batch-archive", response_model=AssetBatchOperationResponse)
async def batch_archive_workspace_assets(
    workspace_id: int,
    request: AssetBatchArchiveRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetBatchOperationResponse:
    """批量归档 active 普通资源，并返回逐项失败原因。"""

    result = await AssetService(session).batch_archive_assets(
        workspace_id,
        request.asset_ids,
        archive_reason=request.archive_reason,
    )
    return AssetBatchOperationResponse.model_validate(result)


@router.post("/workspaces/{workspace_id}/assets/export-package")
async def export_workspace_asset_package(
    workspace_id: int,
    request: AssetPackageExportRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """导出资源离线包，包含原始文件及标签、描述等元数据。"""

    archive_content, filename = await AssetPackageService(session).export_package(
        workspace_id=workspace_id,
        asset_ids=request.asset_ids,
    )
    return Response(
        content=archive_content,
        media_type="application/zip",
        headers={"Content-Disposition": _build_download_content_disposition(filename)},
    )


@router.post("/workspaces/{workspace_id}/assets/import-package", response_model=AssetPackageImportResult)
async def import_workspace_asset_package(
    workspace_id: int,
    archive: Annotated[UploadFile, File(...)],
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetPackageImportResult:
    """导入资源离线包，创建缺失资源并同步同名同文件资源的元数据。"""

    archive_content = await archive.read()
    return await AssetPackageService(session).import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
    )


@router.post("/workspaces/{workspace_id}/assets/{asset_id}/restore", response_model=AssetResponse)
async def restore_workspace_asset(
    workspace_id: int,
    asset_id: int,
    request: AssetRestoreRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetResponse:
    """恢复普通归档资源；历史副本不可直接恢复。"""

    asset = await AssetService(session).restore_asset(workspace_id, asset_id, restore_reason=request.restore_reason)
    return await _build_asset_response(session, workspace_id, asset)


@router.get("/workspaces/{workspace_id}/assets/{asset_id}/references", response_model=AssetReferenceSummary)
async def preview_workspace_asset_references(
    workspace_id: int,
    asset_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetReferenceSummary:
    """预览资源引用关系，用于删除阻断说明。"""

    return await AssetService(session).preview_asset_references(workspace_id, asset_id)


@router.delete("/workspaces/{workspace_id}/assets/{asset_id}", status_code=204)
async def delete_workspace_asset(
    workspace_id: int,
    asset_id: int,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """删除已归档且无业务引用的资源。"""

    await AssetService(session).delete_asset(workspace_id, asset_id)


@router.post("/workspaces/{workspace_id}/assets/batch-delete", response_model=AssetBatchOperationResponse)
async def batch_delete_workspace_assets(
    workspace_id: int,
    request: AssetBatchDeleteRequest,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AssetBatchOperationResponse:
    """批量删除 archived 或历史资源，并返回逐项失败原因。"""

    result = await AssetService(session).batch_delete_assets(workspace_id, request.asset_ids)
    return AssetBatchOperationResponse.model_validate(result)


def _build_download_content_disposition(filename: str) -> str:
    """构建兼容中文文件名的下载响应头。"""

    encoded_name = urllib.parse.quote(filename)
    return f"attachment; filename*=UTF-8''{encoded_name}"
