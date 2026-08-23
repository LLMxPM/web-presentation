"""文件功能：提供 External API 的 Runtime Kit 能力目录与工作空间字体查询。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.common import ListQuery, PagedResponse
from app.schemas.font import WorkspaceFontConfigResponse
from app.schemas.runtime_kit import (
    RuntimeKitCapabilityItem,
    RuntimeKitCapabilityKind,
    RuntimeKitCapabilityListResponse,
)
from app.services.runtime_kit_component_capability_service import RuntimeKitComponentCapabilityService
from app.services.workspace_font_service import WorkspaceFontService

router = APIRouter()


@router.get("/runtime-kit", response_model=RuntimeKitCapabilityListResponse)
async def list_runtime_kit(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("runtime_kit.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    keyword: str | None = None,
    category: str | None = None,
    kind: RuntimeKitCapabilityKind | None = None,
    base_name: str | None = None,
    version_no: int | None = None,
    include_all_versions: bool = False,
) -> RuntimeKitCapabilityListResponse:
    """查询带版本化公开路径的 Runtime Kit 能力。"""

    return RuntimeKitComponentCapabilityService(session).list_components(
        keyword=keyword,
        category=category,
        kind=kind,
        base_name=base_name,
        version_no=version_no,
        include_all_versions=include_all_versions,
    )


@router.get("/runtime-kit/{item}", response_model=RuntimeKitCapabilityItem)
async def get_runtime_kit(
    item: str,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("runtime_kit.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RuntimeKitCapabilityItem:
    """获取单项 Runtime Kit 能力详情。"""

    return RuntimeKitComponentCapabilityService(session).get_component(item)


@router.get("/fonts", response_model=PagedResponse[WorkspaceFontConfigResponse])
async def list_fonts(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("font.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    x_workspace_id: Annotated[int, Header(alias="X-Workspace-ID", description="目标工作空间 ID")],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
) -> PagedResponse[WorkspaceFontConfigResponse]:
    """查询工作空间注册字体。"""

    query = ListQuery(page=page, page_size=page_size, keyword=keyword)
    return await WorkspaceFontService(session).list_workspace_fonts(x_workspace_id, query)
