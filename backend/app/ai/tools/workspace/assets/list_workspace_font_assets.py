"""文件功能：定义工作空间已注册字体资源查询工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import RESOURCE_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.models.font import WorkspaceFontConfig


def build_list_workspace_font_assets_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建已注册字体资源查询工具。"""

    @agent_tool(show_result=False)
    async def list_workspace_font_assets(
        run_context: AgentToolContext,
        keyword: str | None = None,
        description_keyword: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, str | None]]:
        """查询当前工作空间内已注册并可用的字体资源。"""

        dependencies, _ = await resolve_tool_context(
            session_factory,
            run_context,
            required_scopes=RESOURCE_TOOL_READ_SCOPES,
            required_dependency_fields=("workspace_id",),
        )
        workspace_id = int(dependencies["workspace_id"])

        async with session_factory() as session:
            result = await session.execute(
                select(WorkspaceAsset, WorkspaceFontConfig)
                .join(WorkspaceFontConfig, WorkspaceFontConfig.asset_id == WorkspaceAsset.id)
                .where(WorkspaceAsset.workspace_id == workspace_id)
                .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                .where(WorkspaceAsset.source_asset_id.is_(None))
                .where(WorkspaceFontConfig.workspace_id == workspace_id)
                .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
                .order_by(WorkspaceFontConfig.updated_at.desc(), WorkspaceFontConfig.id.desc())
            )
            normalized_keyword = str(keyword or "").strip().lower()
            normalized_description_keyword = str(description_keyword or "").strip().lower()
            normalized_tags = [str(item).strip().lower() for item in tags or [] if str(item).strip()]
            bounded_limit = max(1, min(int(limit), 100))

            payload: list[dict[str, str | None]] = []
            for asset, font_config in result.all():
                if normalized_keyword and normalized_keyword not in asset.name.lower():
                    continue
                description = str(asset.description or "")
                if normalized_description_keyword and normalized_description_keyword not in description.lower():
                    continue
                asset_tags = [str(item).strip().lower() for item in asset.tags or [] if str(item).strip()]
                if normalized_tags and not all(tag in asset_tags for tag in normalized_tags):
                    continue
                payload.append(
                    {
                        "name": asset.name,
                        "asset_name": asset.name,
                        "font_family": font_config.font_family,
                        "font_weight": font_config.font_weight,
                        "font_style": font_config.font_style,
                        "font_display": font_config.font_display,
                        "extension": _extract_extension(asset.original_name),
                        "type": "font",
                        "description": asset.description,
                    }
                )
                if len(payload) >= bounded_limit:
                    break
            return payload

    return list_workspace_font_assets


def _extract_extension(file_name: str) -> str | None:
    """从字体文件名中提取扩展名。"""

    suffix = Path(str(file_name or "")).suffix.lstrip(".").lower()
    return suffix or None
