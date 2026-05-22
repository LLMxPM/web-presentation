"""文件功能：提供 Runtime Kit 内建能力目录与只读预览接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db_session
from app.schemas.release import PreviewArtifactResponse
from app.schemas.runtime_kit import (
    RuntimeKitCapabilityItem,
    RuntimeKitCapabilityKind,
    RuntimeKitCapabilityListResponse,
    RuntimeKitComponentPreviewRequest,
)
from app.services.auth_service import AuthContext
from app.services.runtime_kit_component_capability_service import RuntimeKitComponentCapabilityService

router = APIRouter()


@router.get("/components", response_model=RuntimeKitCapabilityListResponse)
@router.get("/capabilities", response_model=RuntimeKitCapabilityListResponse)
async def list_runtime_kit_components(
    keyword: str | None = None,
    category: str | None = None,
    kind: RuntimeKitCapabilityKind | None = None,
    previewable: bool | None = None,
    _: Annotated[AuthContext, Depends(get_current_user)] = None,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> RuntimeKitCapabilityListResponse:
    """查询 Runtime Kit 内建能力目录。"""

    return RuntimeKitComponentCapabilityService(session).list_components(
        keyword=keyword,
        category=category,
        kind=kind,
        previewable=previewable,
    )


@router.get("/components/{name}", response_model=RuntimeKitCapabilityItem)
@router.get("/capabilities/{name}", response_model=RuntimeKitCapabilityItem)
async def get_runtime_kit_component(
    name: str,
    _: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RuntimeKitCapabilityItem:
    """读取单个 Runtime Kit 内建能力详情。"""

    return RuntimeKitComponentCapabilityService(session).get_component(name)


@router.post("/components/{name}/preview-artifacts", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
@router.post("/capabilities/{name}/preview-artifacts", response_model=PreviewArtifactResponse, response_model_exclude_none=True)
async def create_runtime_kit_component_preview_artifact(
    name: str,
    payload: RuntimeKitComponentPreviewRequest,
    current: Annotated[AuthContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PreviewArtifactResponse:
    """为 Runtime Kit 可预览组件能力创建只读组件预览 artifact。"""

    tenant_id = f"tenant_{current.user.id}"
    return await RuntimeKitComponentCapabilityService(session).create_preview_artifact(
        name=name,
        workspace_id=payload.workspace_id,
        preview_options=payload.preview_options,
        tenant_id=tenant_id,
    )
