"""文件功能：定义工作空间图标资源查询工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PAGE_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType, RecordStatus
from app.services.asset_render_metadata_service import AssetRenderMetadataService


def build_list_workspace_icon_assets_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建图标资源查询工具。"""

    @agent_tool(show_result=False)
    async def list_workspace_icon_assets(
        run_context: AgentToolContext,
        keyword: str | None = None,
        description_keyword: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, str | float | None]]:
        """查询当前工作空间内可用的图标资源。"""

        dependencies, _ = await resolve_tool_context(session_factory, run_context, required_scopes=PAGE_TOOL_READ_SCOPES)
        workspace_id = int(dependencies["workspace_id"])

        async with session_factory() as session:
            assets = await _list_assets(session, workspace_id, {AssetType.ICON.value})
            return _filter_and_dump_assets(
                assets=assets,
                expected_type="icon",
                keyword=keyword,
                description_keyword=description_keyword,
                tags=tags,
                limit=limit,
            )

    return list_workspace_icon_assets


async def _list_assets(session: AsyncSession, workspace_id: int, asset_types: set[str]) -> list[WorkspaceAsset]:
    """按工作空间与资源类型批量读取资产。"""

    result = await session.execute(
        select(WorkspaceAsset)
        .where(WorkspaceAsset.workspace_id == workspace_id)
        .where(WorkspaceAsset.asset_type.in_(sorted(asset_types)))
        .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
        .where(WorkspaceAsset.source_asset_id.is_(None))
        .order_by(WorkspaceAsset.updated_at.desc(), WorkspaceAsset.id.desc())
    )
    return list(result.scalars().all())


def _filter_and_dump_assets(
    *,
    assets: list[WorkspaceAsset],
    expected_type: str,
    keyword: str | None,
    description_keyword: str | None,
    tags: list[str] | None,
    limit: int,
) -> list[dict[str, str | float | None]]:
    """根据关键词、描述与标签过滤资产并输出精简结果。"""

    normalized_keyword = str(keyword or "").strip().lower()
    normalized_description_keyword = str(description_keyword or "").strip().lower()
    normalized_tags = [str(item).strip().lower() for item in tags or [] if str(item).strip()]
    bounded_limit = max(1, min(int(limit), 100))

    filtered_assets: list[dict[str, str | None]] = []
    for asset in assets:
        if normalized_keyword and normalized_keyword not in asset.name.lower():
            continue
        description = str(asset.description or "")
        if normalized_description_keyword and normalized_description_keyword not in description.lower():
            continue
        asset_tags = [str(item).strip().lower() for item in asset.tags or [] if str(item).strip()]
        if normalized_tags and not all(tag in asset_tags for tag in normalized_tags):
            continue
        ratio_summary = AssetRenderMetadataService.summarize_metadata(asset.render_metadata)
        filtered_assets.append({
            "name": asset.name,
            "extension": _extract_extension(asset.original_name),
            "type": expected_type,
            "description": asset.description,
            "approx_aspect_ratio": ratio_summary["approx_aspect_ratio"],
            "approx_aspect_ratio_value": ratio_summary["approx_aspect_ratio_value"],
            "aspect_ratio_source": ratio_summary["aspect_ratio_source"],
        })
        if len(filtered_assets) >= bounded_limit:
            break
    return filtered_assets


def _extract_extension(file_name: str) -> str | None:
    """从文件名中提取扩展名。"""

    suffix = Path(str(file_name or "")).suffix.lstrip(".").lower()
    return suffix or None
