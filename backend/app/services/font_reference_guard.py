"""文件功能：保护主题绑定字体族的最后一个可用字体面，避免移动后留下空引用。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.tx import acquire_row_write_lock
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.models.font import WorkspaceFontConfig, WorkspaceFontFamily
from app.models.workspace_theme import WorkspaceTheme


async def is_last_referenced_font_face(
    session: AsyncSession, face: WorkspaceFontConfig, *, target_family_id: int | None = None,
) -> bool:
    """锁定来源族后判断是否为主题必需的最后一个可用 face，供移动、停用与删除共享。"""

    # 来源/目标按 ID 顺序锁定，避免两个方向相反的移动交叉等待。
    family_ids = {face.family_id}
    if target_family_id is not None:
        family_ids.add(target_family_id)
    for family_id in sorted(family_ids):
        await acquire_row_write_lock(session, WorkspaceFontFamily, family_id)
    if face.status != RecordStatus.ACTIVE.value:
        return False
    referenced = await session.scalar(
        select(WorkspaceTheme.id)
        .where(WorkspaceTheme.workspace_id == face.workspace_id, WorkspaceTheme.deleted_at.is_(None))
        .where(
            (WorkspaceTheme.heading_font_family_id == face.family_id)
            | (WorkspaceTheme.body_font_family_id == face.family_id)
            | (WorkspaceTheme.code_font_family_id == face.family_id)
        )
        .limit(1)
    )
    if referenced is None:
        return False
    sibling = await session.scalar(
        select(WorkspaceFontConfig.id)
        .join(WorkspaceAsset, WorkspaceFontConfig.asset_id == WorkspaceAsset.id)
        .where(
            WorkspaceFontConfig.workspace_id == face.workspace_id,
            WorkspaceFontConfig.family_id == face.family_id,
            WorkspaceFontConfig.id != face.id,
            WorkspaceFontConfig.status == RecordStatus.ACTIVE.value,
            WorkspaceAsset.workspace_id == face.workspace_id,
            WorkspaceAsset.asset_type == AssetType.FONT.value,
            WorkspaceAsset.status == RecordStatus.ACTIVE.value,
            WorkspaceAsset.archived_at.is_(None),
            WorkspaceAsset.source_asset_id.is_(None),
            WorkspaceAsset.history_kind.is_(None),
        )
        .limit(1)
    )
    return sibling is None


async def ensure_font_face_can_leave_family(
    session: AsyncSession, face: WorkspaceFontConfig, *, target_family_id: int | None = None,
) -> None:
    """拒绝移走或停用主题所需的最后一个可用 face，失败交由调用方整体回滚。"""

    if await is_last_referenced_font_face(session, face, target_family_id=target_family_id):
        raise AppException(
            status_code=409, code="FONT_CONFIG_IN_USE",
            detail="该字体是主题所绑定字体族的最后一个可用文件，请先切换主题字体后再移动或停用。",
        )
