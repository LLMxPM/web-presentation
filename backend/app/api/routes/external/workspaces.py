"""文件功能：提供 External API v1 工作空间查询与能力发现接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies_external import ExternalAuthContext, require_external_operation
from app.core.external_operations import OPERATION_REGISTRY
from app.db.session import get_db_session
from app.models.enums import RecordStatus
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.external_api import ExternalCapabilitiesResponse
from app.schemas.workspace import WorkspaceItem
from app.services.workspace_service import WorkspaceService

router = APIRouter()


@router.get("", response_model=list[WorkspaceItem])
async def list_authorized_workspaces(
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("workspace.list"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[WorkspaceItem]:
    """查询当前 PAT 授权且用户具有 active 成员资格的工作空间列表。"""

    stmt = (
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == auth.user.id)
        .where(WorkspaceMember.status == RecordStatus.ACTIVE.value)
        .where(Workspace.status == RecordStatus.ACTIVE.value)
        .order_by(Workspace.id.asc())
    )
    if not auth.all_workspaces:
        stmt = stmt.where(Workspace.id.in_(auth.workspace_ids))
    workspaces = (await session.scalars(stmt)).all()
    return [await WorkspaceService(session)._to_item(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceItem)
async def get_workspace_detail(
    workspace_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("workspace.get"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkspaceItem:
    """获取指定工作空间信息。"""

    await auth.ensure_workspace_access(workspace_id, session)

    return await WorkspaceService(session).get(workspace_id, user_id=auth.user.id)


@router.get("/{workspace_id}/capabilities", response_model=ExternalCapabilitiesResponse)
async def get_workspace_capabilities(
    workspace_id: int,
    auth: Annotated[ExternalAuthContext, Depends(require_external_operation("system.capabilities"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExternalCapabilitiesResponse:
    """获取当前令牌在目标工作空间中允许执行的操作清单。"""

    await auth.ensure_workspace_access(workspace_id, session)

    # 过滤当前 Token 具备全部 Scope 且在当前空间可执行的操作
    available_ops = [
        op_key
        for op_key, spec in OPERATION_REGISTRY.items()
        if auth.has_required_scopes(spec.scopes, mode=spec.scope_mode)
    ]

    return ExternalCapabilitiesResponse(
        version="v1",
        workspace_id=workspace_id,
        scopes=sorted(list(auth.scopes)),
        operations=sorted(available_ops),
    )
