"""文件功能：提供工作空间组件的列表、创建、更新、删除、版本查询与离线分享包接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.models.enums import WorkspaceComponentType
from app.schemas.common import MessageResponse, PagedResponse
from app.schemas.component import (
    ComponentShareExportValidationResult,
    ComponentShareImportResult,
    ComponentShareImportValidationResult,
    WorkspaceComponentCreateRequest,
    WorkspaceComponentCurrentDependencies,
    WorkspaceComponentExportPackageRequest,
    WorkspaceComponentItem,
    WorkspaceComponentListQuery,
    WorkspaceComponentPublishRequest,
    WorkspaceComponentReferenceUpgradeRequest,
    WorkspaceComponentReferenceUpgradeResponse,
    WorkspaceComponentReferences,
    WorkspaceComponentRestoreDraftRequest,
    WorkspaceComponentSourcePreviewRequest,
    WorkspaceComponentUpdateRequest,
    WorkspaceComponentVersionContent,
    WorkspaceComponentVersionListItem,
)
from app.schemas.release import PreviewArtifactResponse
from app.services.auth_service import AuthContext
from app.services.component_reference_service import ComponentReferenceService
from app.services.component_share_package_service import ComponentSharePackageService
from app.services.component_preview_service import ComponentPreviewService
from app.services.workspace_component_service import WorkspaceComponentService
from app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.post("/export-package")
async def export_component_package(
    payload: WorkspaceComponentExportPackageRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    """导出工作空间组件离线分享包。"""

    await WorkspaceService(session).ensure_access(payload.workspace_id, user_id=current.user.id)
    archive_content, filename = await ComponentSharePackageService(session).export_package(
        workspace_id=payload.workspace_id,
        component_ids=payload.component_ids,
        manual_asset_names=payload.manual_asset_names,
    )
    return Response(
        content=archive_content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export-package/validate", response_model=ComponentShareExportValidationResult)
async def validate_component_package_export(
    payload: WorkspaceComponentExportPackageRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ComponentShareExportValidationResult:
    """预检工作空间组件离线分享包导出资源，不生成 Zip。"""

    await WorkspaceService(session).ensure_access(payload.workspace_id, user_id=current.user.id)
    return await ComponentSharePackageService(session).validate_export_package(
        workspace_id=payload.workspace_id,
        component_ids=payload.component_ids,
        manual_asset_names=payload.manual_asset_names,
    )


@router.post("/import-package/validate", response_model=ComponentShareImportValidationResult)
async def validate_component_package_import(
    workspace_id: Annotated[int, Form()],
    archive: Annotated[UploadFile, File(...)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ComponentShareImportValidationResult:
    """预检组件离线分享包，不写入数据库。"""

    await WorkspaceService(session).ensure_access(workspace_id, user_id=current.user.id)
    archive_content = await archive.read()
    return await ComponentSharePackageService(session).validate_import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
    )


@router.post("/import-package", response_model=ComponentShareImportResult)
async def import_component_package(
    workspace_id: Annotated[int, Form()],
    archive: Annotated[UploadFile, File(...)],
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ComponentShareImportResult:
    """正式导入组件离线分享包。"""

    archive_content = await archive.read()
    await WorkspaceService(session).ensure_access(workspace_id, user_id=current.user.id)
    return await ComponentSharePackageService(session).import_package(
        workspace_id=workspace_id,
        archive_content=archive_content,
        operator_id=current.user.id,
    )


@router.get("", response_model=PagedResponse[WorkspaceComponentItem])
async def list_components(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    keyword: str | None = None,
    component_type: WorkspaceComponentType | None = None,
    status: str | None = None,
    sort_by: str = "updated_at",
    sort_order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    workspace_id: int | None = None,
    published_only: bool = False,
    current: Annotated[AuthContext, Depends(get_current_user)] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> PagedResponse[WorkspaceComponentItem]:
    """查询工作空间组件列表。"""

    query = WorkspaceComponentListQuery(
        page=page,
        page_size=page_size,
        keyword=keyword,
        component_type=component_type,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        workspace_id=workspace_id,
        published_only=published_only,
    )
    return await WorkspaceComponentService(session).list(query, user_id=current.user.id)


@router.get("/{component_id}", response_model=WorkspaceComponentItem)
async def get_component(
    component_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentItem:
    """查询单个组件详情。"""

    return await WorkspaceComponentService(session).get(component_id, user_id=current.user.id)


@router.get("/{component_id}/current-dependencies", response_model=WorkspaceComponentCurrentDependencies)
async def get_component_current_dependencies(
    component_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentCurrentDependencies:
    """查询组件当前版本的源码依赖索引。"""

    return await WorkspaceComponentService(session).get_current_dependencies(component_id, user_id=current.user.id)


@router.get("/{component_id}/references", response_model=WorkspaceComponentReferences)
async def get_component_references(
    component_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentReferences:
    """查询组件被当前页面版本和当前组件发布版本直接引用的情况。"""

    return await ComponentReferenceService(session).get_references(component_id, user_id=current.user.id)


@router.post("/{component_id}/references/upgrade", response_model=WorkspaceComponentReferenceUpgradeResponse)
async def upgrade_component_references(
    component_id: int,
    payload: WorkspaceComponentReferenceUpgradeRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentReferenceUpgradeResponse:
    """批量升级页面和组件草稿中对指定组件的直接引用版本。"""

    return await ComponentReferenceService(session).upgrade_references(component_id, payload, user_id=current.user.id)


@router.post("/preview-artifacts/from-source", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_component_source_preview_artifact(
    payload: WorkspaceComponentSourcePreviewRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """基于未保存组件源码生成临时组件预览 artifact。"""

    await WorkspaceService(session).ensure_access(payload.workspace_id, user_id=current.user.id)
    tenant_id = f"tenant_{current.user.id}"
    return await ComponentPreviewService(session).create_source_preview_artifact(
        workspace_id=payload.workspace_id,
        component_id=payload.component_id,
        component_name=payload.component_name,
        content=payload.content,
        preview_schema=payload.preview_schema,
        preview_options=payload.preview_options,
        tenant_id=tenant_id,
        file_type=payload.file_type,
    )


@router.post("/{component_id}/preview-artifacts", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_component_preview_artifact(
    component_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """为组件最新已发布版本生成无状态组件预览 artifact。"""

    await WorkspaceComponentService(session).get(component_id, user_id=current.user.id)
    tenant_id = f"tenant_{current.user.id}"
    return await ComponentPreviewService(session).create_preview_artifact(component_id, tenant_id)


@router.post("", response_model=WorkspaceComponentItem)
async def create_component(
    payload: WorkspaceComponentCreateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentItem:
    """创建工作空间组件。"""

    return await WorkspaceComponentService(session).create(payload, current.user.id)


@router.patch("/{component_id}", response_model=WorkspaceComponentItem)
async def update_component(
    component_id: int,
    payload: WorkspaceComponentUpdateRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentItem:
    """更新工作空间组件。"""

    return await WorkspaceComponentService(session).update(component_id, payload, current.user.id)


@router.post("/{component_id}/publish", response_model=WorkspaceComponentItem)
async def publish_component(
    component_id: int,
    payload: WorkspaceComponentPublishRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentItem:
    """将组件当前草稿发布为正式版本。"""

    return await WorkspaceComponentService(session).publish(component_id, payload, current.user.id)


@router.get("/{component_id}/versions", response_model=list[WorkspaceComponentVersionListItem])
async def list_component_versions(
    component_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WorkspaceComponentVersionListItem]:
    """查询组件版本历史。"""

    return await WorkspaceComponentService(session).list_versions(component_id, user_id=current.user.id)


@router.get("/{component_id}/versions/{version_no}", response_model=WorkspaceComponentVersionContent)
async def get_component_version_content(
    component_id: int,
    version_no: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentVersionContent:
    """查询指定组件版本的完整源码。"""

    return await WorkspaceComponentService(session).get_version_content(component_id, version_no, user_id=current.user.id)


@router.post("/{component_id}/versions/{version_no}/restore-to-draft", response_model=WorkspaceComponentItem)
async def restore_component_version_to_draft(
    component_id: int,
    version_no: int,
    payload: WorkspaceComponentRestoreDraftRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceComponentItem:
    """将指定组件发布版本恢复到草稿区。"""

    return await WorkspaceComponentService(session).restore_version_to_draft(
        component_id,
        version_no,
        payload,
        current.user.id,
    )


@router.post("/{component_id}/versions/{version_no}/preview-artifact", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_component_version_preview_artifact(
    component_id: int,
    version_no: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """为组件指定发布版本生成无状态组件预览 artifact。"""

    await WorkspaceComponentService(session).get(component_id, user_id=current.user.id)
    tenant_id = f"tenant_{current.user.id}"
    return await ComponentPreviewService(session).create_version_preview_artifact(component_id, version_no, tenant_id)


@router.delete("/{component_id}", response_model=MessageResponse)
async def delete_component(
    component_id: int,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    """删除指定工作空间组件。"""

    await WorkspaceComponentService(session).delete(component_id, user_id=current.user.id)
    return MessageResponse(message="组件已删除。")
