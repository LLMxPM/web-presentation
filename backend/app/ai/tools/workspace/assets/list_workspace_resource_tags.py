"""文件功能：定义工作空间资源标签查询工具。"""

from __future__ import annotations

from typing import Any

from app.ai.platform_tools import AgentToolContext, agent_tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import PAGE_TOOL_READ_SCOPES
from app.ai.tools.shared import resolve_tool_context
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus


def build_list_workspace_resource_tags_tool(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    """构建工作空间资源标签查询工具。"""

    @agent_tool(show_result=False)
    async def list_workspace_resource_tags(
        run_context: AgentToolContext,
        keyword: str | None = None,
        limit: int = 100,
    ) -> list[str]:
        """查询当前工作空间已有资源标签。"""

        dependencies, _ = await resolve_tool_context(session_factory, run_context, required_scopes=PAGE_TOOL_READ_SCOPES)
        workspace_id = int(dependencies["workspace_id"])
        normalized_keyword = str(keyword or "").strip().lower()
        bounded_limit = max(1, min(int(limit), 100))

        async with session_factory() as session:
            result = await session.execute(
                select(WorkspaceAsset.tags)
                .where(WorkspaceAsset.workspace_id == workspace_id)
                .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
                .where(WorkspaceAsset.source_asset_id.is_(None))
                .order_by(WorkspaceAsset.updated_at.desc(), WorkspaceAsset.id.desc())
            )
            resolved_tags: list[str] = []
            seen: set[str] = set()
            for tag_list in result.scalars():
                for tag in tag_list or []:
                    normalized_tag = str(tag).strip()
                    if not normalized_tag:
                        continue
                    lower_tag = normalized_tag.lower()
                    if normalized_keyword and normalized_keyword not in lower_tag:
                        continue
                    if lower_tag in seen:
                        continue
                    seen.add(lower_tag)
                    resolved_tags.append(normalized_tag)
                    if len(resolved_tags) >= bounded_limit:
                        return resolved_tags
            return resolved_tags

    return list_workspace_resource_tags
