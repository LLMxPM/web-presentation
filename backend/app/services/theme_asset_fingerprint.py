"""文件功能：收集主题 Logo 和注册字体的实时文件身份，防止同名替换复用旧检查/截图。"""
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import WorkspaceAsset
from app.models.font import WorkspaceFontConfig


async def collect_theme_asset_identity(
    session: AsyncSession, *, workspace_id: int,
    theme_config: dict[str, object], fonts: Sequence[WorkspaceFontConfig],
) -> list[dict[str, object]]:
    """批量读取字体与主题 Logo 的内容 hash/可用性；未引用资源和非画布 favicon 不参与。"""
    names: set[str] = set()
    themes = theme_config.get("themes")
    if isinstance(themes, dict):
        for theme in themes.values():
            if isinstance(theme, dict):
                for field in ("logo", "invertLogo"):
                    name = theme.get(field)
                    if isinstance(name, str) and name.strip():
                        names.add(name.strip())
    asset_ids = [font.asset_id for font in fonts]
    if not names and not asset_ids:
        return []
    assets = (await session.scalars(
        select(WorkspaceAsset).where(
            WorkspaceAsset.workspace_id == workspace_id,
            or_(WorkspaceAsset.id.in_(asset_ids), WorkspaceAsset.name.in_(names)),
        ).order_by(WorkspaceAsset.id)
    )).all()
    return [{
        "id": asset.id, "name": asset.name, "file_hash": asset.file_hash,
        "asset_type": asset.asset_type, "status": asset.status,
        "archived_at": asset.archived_at.isoformat() if asset.archived_at else None,
        "source_asset_id": asset.source_asset_id, "history_kind": asset.history_kind,
    } for asset in assets]
