"""文件功能：提供 External API 的 Runtime Kit 能力目录查询。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.db.session import get_db_session
from app.schemas.runtime_kit import (
    RuntimeKitCapabilityItem,
    RuntimeKitCapabilityKind,
    RuntimeKitCapabilityListResponse,
)
from app.services.runtime_kit_component_capability_service import RuntimeKitComponentCapabilityService

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
