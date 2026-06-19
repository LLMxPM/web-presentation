"""文件功能：定义工作空间可渲染内容资源查询工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PAGE_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.ai.tools.workspace.assets.list_workspace_icon_assets import _filter_and_dump_assets, _list_assets
from app.models.enums import AssetType


CONTENT_RENDER_TYPES = {
    AssetType.IMAGE.value,
    AssetType.VIDEO.value,
    AssetType.DRAWIO.value,
    AssetType.MERMAID.value,
    AssetType.CHART.value,
    AssetType.FORMULA.value,
}


def build_list_workspace_render_assets_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建页面内容渲染资源查询工具。"""

    @agent_tool(show_result=False)
    async def list_workspace_render_assets(
        run_context: AgentToolContext,
        render_type: str | None = None,
        keyword: str | None = None,
        description_keyword: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, str | None]]:
        """查询当前工作空间内可渲染在页面区域中的资源。"""

        dependencies, _ = await resolve_tool_context(session_factory, run_context, required_scopes=PAGE_TOOL_READ_SCOPES)
        workspace_id = int(dependencies["workspace_id"])
        normalized_render_type = str(render_type or "").strip().lower()
        if normalized_render_type and normalized_render_type not in CONTENT_RENDER_TYPES:
            return []
        asset_types = {normalized_render_type} if normalized_render_type else CONTENT_RENDER_TYPES

        async with session_factory() as session:
            assets = await _list_assets(session, workspace_id, asset_types)
            return _filter_and_dump_assets(
                assets=assets,
                expected_type=normalized_render_type or "render",
                keyword=keyword,
                description_keyword=description_keyword,
                tags=tags,
                limit=limit,
            )

    return list_workspace_render_assets
